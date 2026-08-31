"""LocalStorageBackend — SQLite via SQLAlchemy. Structured data only; resume
files and semantic-summary markdown are written separately by mirror_writer.py
into the on-disk candidates/ tree."""

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    func,
    inspect,
    or_,
    select,
    text,
)
from sqlalchemy.orm import Session, sessionmaker

from app.models.db import Base, Candidate, IngestScanHistoryEntry, ResumeSource, SearchHistoryEntry, User

_SORT_COLUMNS = {
    "recent": (Candidate.date_submitted, True),
    "oldest": (Candidate.date_submitted, False),
    "name_asc": (Candidate.legal_first_name, False),
    "name_desc": (Candidate.legal_first_name, True),
}
from app.storage.base import BaseStorageBackend

# SQLite column type -> DDL type, for auto-migration below. Falls back to
# TEXT for anything unrecognized (safe: SQLite is dynamically typed anyway).
_DDL_TYPE_BY_PYTHON_TYPE = {
    JSON: "JSON",
    Boolean: "BOOLEAN",
    DateTime: "DATETIME",
    Float: "FLOAT",
    Integer: "INTEGER",
    String: "VARCHAR",
    Text: "TEXT",
}


def _default_sql_for(column) -> str:
    """Existing rows get whatever this returns for a newly-added column.
    Most columns here use a Python-level default (`default=list`,
    `default=dict`, `default=""`, `default=0.0`) that only applies on
    INSERT through the ORM — a plain ALTER TABLE has no way to run that
    Python callable, so without this, every pre-existing row would get NULL
    instead. `list`/`dict` are handled explicitly since every JSON column in
    this schema uses one of those two; anything else falls back to the
    scalar case SQLAlchemy already models for us."""
    if column.default is None:
        return ""
    if not column.default.is_scalar:
        # A no-arg callable default (`default=list`, `default=dict`) is
        # wrapped by SQLAlchemy into a `(ctx) -> value` function, so it's no
        # longer literally `is list`/`is dict` — call it to see what it
        # actually produces instead of comparing identity.
        try:
            produced = column.default.arg(None)
        except TypeError:
            return ""
        if produced == []:
            return " DEFAULT '[]'"
        if produced == {}:
            return " DEFAULT '{}'"
        return ""
    default_value = column.default.arg
    if isinstance(default_value, bool):
        return f" DEFAULT {int(default_value)}"
    if isinstance(default_value, (int, float)):
        return f" DEFAULT {default_value}"
    if isinstance(default_value, str):
        return f" DEFAULT '{default_value}'"
    return ""


def _add_missing_columns(engine) -> None:
    """`Base.metadata.create_all()` only creates tables that don't exist yet
    — it never alters an existing table to add a column a newer model
    version introduced (this bit us directly: adding `Candidate.embedding`
    broke every existing database with `no such column: candidates.embedding`
    until it was restarted against a *fresh* db). This walks every mapped
    table, diffs its columns against what's actually in the database via
    PRAGMA table_info, and ALTERs in whatever's missing — so a schema change
    in code never requires a manual migration step or a wiped database
    again."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table — create_all already handled it
            existing_columns = {row["name"] for row in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                ddl_type = _DDL_TYPE_BY_PYTHON_TYPE.get(type(column.type), "TEXT")
                default_sql = _default_sql_for(column)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}{default_sql}'))


class LocalStorageBackend(BaseStorageBackend):
    def __init__(self, sqlite_path: str):
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self._engine)
        _add_missing_columns(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)

    def session(self) -> Session:
        return self._session_factory()

    def find_candidate_by_fingerprint(self, session: Session, fingerprint: str) -> Candidate | None:
        return session.execute(
            select(Candidate).where(Candidate.identity_fingerprint == fingerprint)
        ).scalar_one_or_none()

    def upsert_candidate(self, session: Session, candidate: Candidate) -> Candidate:
        session.add(candidate)
        session.flush()
        return candidate

    def add_resume_source(self, session: Session, source: ResumeSource) -> ResumeSource:
        session.add(source)
        session.flush()
        return source

    def find_resume_source_by_hash(self, session: Session, content_hash: str, source_ref: str) -> ResumeSource | None:
        return session.execute(
            select(ResumeSource).where(
                ResumeSource.content_hash == content_hash, ResumeSource.source_ref == source_ref
            )
        ).scalars().first()

    def candidates_page(
        self,
        session: Session,
        start: datetime | None,
        end: datetime | None,
        source: str | None,
        query: str | None,
        sort: str,
        limit: int,
        offset: int,
        skills: list[str] | None = None,
        employment_statuses: list[str] | None = None,
        work_visa_statuses: list[str] | None = None,
        experience_min: float | None = None,
        experience_max: float | None = None,
    ) -> tuple[list[Candidate], int]:
        """Filters + sorts + pages entirely in SQL instead of loading every
        matching candidate into Python and slicing there — the previous
        approach (`candidates_in_date_range`) returned the full result set on
        every call, which is what made All Candidates cost more the larger
        the database got, independent of how many rows the recruiter was
        actually looking at. All filters happen before LIMIT/OFFSET so the
        page and its total count both reflect the same filtered set, and
        combine as AND (a candidate must match every active filter) while
        each multi-select filter (skills/status/visa) is an OR internally —
        e.g. skills=[Python, Go] + employment_statuses=[actively_looking]
        means "(Python or Go) and actively_looking"."""
        conditions = []
        if start:
            conditions.append(Candidate.date_submitted >= start)
        if end:
            conditions.append(Candidate.date_submitted <= end)
        if source:
            conditions.append(
                Candidate.id.in_(select(ResumeSource.candidate_id).where(ResumeSource.origin == source))
            )
        if query:
            like = f"%{query}%"
            conditions.append(
                or_(
                    Candidate.legal_first_name.ilike(like),
                    Candidate.legal_last_name.ilike(like),
                    Candidate.email.ilike(like),
                    Candidate.skills.cast(String).ilike(like),
                )
            )
        if skills:
            # skills is stored as a JSON list — matched via the same
            # cast-to-string ilike approach the free-text search above
            # already uses rather than a JSON1-specific operator, so this
            # stays portable if candidates_page grows a non-SQLite backend.
            conditions.append(
                or_(*[Candidate.skills.cast(String).ilike(f'%"{skill}"%') for skill in skills])
            )
        if employment_statuses:
            conditions.append(Candidate.employment_status.in_(employment_statuses))
        if work_visa_statuses:
            conditions.append(Candidate.work_visa_status.in_(work_visa_statuses))
        if experience_min is not None:
            conditions.append(Candidate.experience_years >= experience_min)
        if experience_max is not None:
            conditions.append(Candidate.experience_years <= experience_max)

        count_stmt = select(func.count()).select_from(Candidate)
        for condition in conditions:
            count_stmt = count_stmt.where(condition)
        total = session.execute(count_stmt).scalar_one()

        column, descending = _SORT_COLUMNS.get(sort, _SORT_COLUMNS["recent"])
        page_stmt = select(Candidate)
        for condition in conditions:
            page_stmt = page_stmt.where(condition)
        page_stmt = page_stmt.order_by(column.desc() if descending else column.asc()).limit(limit).offset(offset)

        return list(session.execute(page_stmt).scalars()), total

    def candidate_facets(self, session: Session) -> tuple[list[str], float]:
        # Skills is a JSON list per row with no relational table behind it,
        # so "distinct skills across the pool" has to be flattened in
        # Python rather than a single SQL DISTINCT — fine at this scale
        # (one skills-list per candidate, not per resume line).
        skill_set: set[str] = set()
        for (skills,) in session.execute(select(Candidate.skills)):
            skill_set.update(skills or [])
        max_experience = session.execute(select(func.max(Candidate.experience_years))).scalar_one() or 0.0
        return sorted(skill_set, key=str.lower), max_experience

    def record_search_history(self, session: Session, entry: SearchHistoryEntry) -> SearchHistoryEntry:
        session.add(entry)
        session.flush()
        return entry

    def record_ingest_scan(self, session: Session, entry: IngestScanHistoryEntry) -> IngestScanHistoryEntry:
        session.add(entry)
        session.flush()
        return entry

    def any_user_exists(self, session: Session) -> bool:
        return session.execute(select(User.id).limit(1)).first() is not None

    def find_user_by_email(self, session: Session, email: str) -> User | None:
        return session.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()

    def create_user(self, session: Session, user: User) -> User:
        session.add(user)
        session.flush()
        return user
