"""
SQLAlchemy ORM models — the structured half of storage (the other half is the
on-disk resume/summary mirror under data/candidates/, written by mirror_writer.py).

Candidates are source-agnostic: a Candidate row can be backed by one or many
ResumeSource rows (email and/or folder), merged via identity_resolution.py.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.utcnow()


class User(Base):
    """Single local recruiter account today (first-run setup creates the one
    row this app checks against). The users table already supports more than
    one row, so multi-user is a login-flow change later, not a schema change."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, default="")
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str] = mapped_column(String, default="")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    criteria_version: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    matches: Mapped[list["Match"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    identity_fingerprint: Mapped[str] = mapped_column(String, index=True, unique=True)

    legal_first_name: Mapped[str] = mapped_column(String, default="")
    legal_middle_name: Mapped[str] = mapped_column(String, default="")
    legal_last_name: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="", index=True)
    phone: Mapped[str] = mapped_column(String, default="")

    employment_status: Mapped[str] = mapped_column(String, default="unknown")
    work_visa_status: Mapped[str] = mapped_column(String, default="unknown")

    skills: Mapped[list] = mapped_column(JSON, default=list)
    experience_years: Mapped[float] = mapped_column(Float, default=0.0)
    education: Mapped[list] = mapped_column(JSON, default=list)
    raw_parsed_profile: Mapped[dict] = mapped_column(JSON, default=dict)

    semantic_summary: Mapped[str] = mapped_column(Text, default="")
    date_submitted: Mapped[datetime] = mapped_column(DateTime, index=True)
    primary_file_path: Mapped[str] = mapped_column(String, default="")

    # Cached at ingest time (see scanning/ingest_service.py) so matching
    # never has to re-embed the whole candidate pool on every run — the
    # single biggest cost in matching at scale. Empty for candidates
    # ingested before this existed; routes/matches.py backfills lazily.
    embedding: Mapped[list] = mapped_column(JSON, default=list)

    # Web presence links — extracted deterministically (regex) from resume
    # text by both the parser and the mock extractor, never LLM-guessed.
    linkedin_url: Mapped[str] = mapped_column(String, default="")
    github_url: Mapped[str] = mapped_column(String, default="")
    portfolio_url: Mapped[str] = mapped_column(String, default="")

    # Dated timeline of every submission that touched this candidate — e.g.
    # a job seeker who applied in 2019, then again in 2022 with new skills
    # after upskilling. Kept as a list of {date, origin, note} dicts, always
    # sorted by date; see scanning/ingest_service.py for how entries are
    # built (ingestion order isn't guaranteed chronological, so entries are
    # sorted on write, not just appended).
    history: Mapped[list] = mapped_column(JSON, default=list)

    # A recruiter's own free-text notes on this person — "why I passed",
    # "call back in Q2" — independent of any one job match (judge_notes and
    # per-flag notes both live on Match, scoped to one job; this doesn't
    # belong to any job). List of {id, text, created_at}, newest first.
    recruiter_notes: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    sources: Mapped[list["ResumeSource"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    matches: Mapped[list["Match"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class ResumeSource(Base):
    """Every time a resume is ingested (email or folder), a row is recorded here —
    even if it resolves to an already-existing Candidate. This is the audit trail
    that lets 'rescan' know what's already been seen from which source."""

    __tablename__ = "resume_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    origin: Mapped[str] = mapped_column(String)  # ResumeOrigin
    source_ref: Mapped[str] = mapped_column(String)  # folder path, or "mailbox:message_id"
    content_hash: Mapped[str] = mapped_column(String, index=True)
    file_path: Mapped[str] = mapped_column(String)
    date_submitted: Mapped[datetime] = mapped_column(DateTime)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # Filenames of other qualifying attachments on the same message (cover
    # letter, portfolio, etc.) that weren't ingested as their own resume —
    # see IngestedResume.additional_attachments.
    additional_attachments: Mapped[list] = mapped_column(JSON, default=list)
    # Deep link to the source email — blank for folder-origin resumes and
    # mock fixtures. See email_ingestor.py.
    email_link: Mapped[str] = mapped_column(String, default="")

    candidate: Mapped["Candidate"] = relationship(back_populates="sources")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))

    score: Mapped[float] = mapped_column(Float)
    tier: Mapped[str] = mapped_column(String)
    reasons: Mapped[dict] = mapped_column(JSON, default=dict)     # {matched: [...], gaps: [...]}
    missing_info: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[list] = mapped_column(JSON, default=list)       # [{color, note, added_by}]
    judge_notes: Mapped[str] = mapped_column(Text, default="")
    criteria_version: Mapped[int] = mapped_column(default=1)
    matched_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    job: Mapped["Job"] = relationship(back_populates="matches")
    candidate: Mapped["Candidate"] = relationship(back_populates="matches")


class Criterion(Base):
    """The criteria *library* — built-in + custom definitions. Whether a given
    criterion applies to a given job, and what value it's set to, lives in
    JobCriterion — a criterion can exist without being selected on any job."""

    __tablename__ = "criteria"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=True)  # null = global library
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_builtin: Mapped[bool] = mapped_column(default=False)
    field_type: Mapped[str] = mapped_column(String, default="text")  # text|number|boolean|select
    options: Mapped[list] = mapped_column(JSON, default=list)  # choices, when field_type == "select"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class JobCriterion(Base):
    """A recruiter's per-job selection of a library criterion: whether it
    applies to this job, and the value they set (a number, a select choice,
    free text) — the 'manually select criteria for each job' feature."""

    __tablename__ = "job_criteria"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    criterion_id: Mapped[str] = mapped_column(ForeignKey("criteria.id"))
    enabled: Mapped[bool] = mapped_column(default=True)
    value: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class SearchHistoryEntry(Base):
    __tablename__ = "search_history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    run_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_range_start: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    date_range_end: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    sources_scanned: Mapped[dict] = mapped_column(JSON, default=dict)  # {folders: [...], mailboxes: [...]}
    candidate_count: Mapped[int] = mapped_column(default=0)
    criteria_version: Mapped[int] = mapped_column(default=1)
    # Set only for a run kicked off as part of a Jobs-page bulk "Match all"/
    # "Match selected" (see stores/bulk-jobs-store.ts, which mints one id per
    # loop and passes it to every job's run) — lets Recent Activity collapse
    # the whole batch into one expandable entry instead of one row per job.
    # Null for a normal single-job "Run matching" click.
    batch_id: Mapped[str] = mapped_column(String, nullable=True, default=None)


class IngestScanHistoryEntry(Base):
    """One row per completed ingest scan (folder or email) — separate from
    SearchHistoryEntry, which logs *matching* runs against a job. Without
    this, the dashboard's Recent Activity had no scan-level record at all:
    it only had individual "Added <candidate>" rows, so a single 600-resume
    scan buried the actual summary under 10 near-identical candidate lines
    (see dashboard/service.py's _recent_activity)."""

    __tablename__ = "ingest_scan_history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    origin: Mapped[str] = mapped_column(String)  # "email" | "folder" | "maintenance" (see routes/maintenance.py)
    source_label: Mapped[str] = mapped_column(String, default="")  # account email(s)/folder path(s), or task label
    resumes_found: Mapped[int] = mapped_column(default=0)
    candidates_created: Mapped[int] = mapped_column(default=0)
    candidates_updated: Mapped[int] = mapped_column(default=0)
    duplicates_skipped: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # Same batching mechanism as SearchHistoryEntry.batch_id, for a Jobs-page
    # bulk "Update matched"/"Update selected" run.
    batch_id: Mapped[str] = mapped_column(String, nullable=True, default=None)
    # Set only for a "rescan matched" run (match_rescan.py) — the job this
    # entry's matched candidates belong to, so Recent Activity can link
    # straight to that job's Match Results instead of falling back to the
    # generic "/app/candidates" every other ingest entry links to.
    job_id: Mapped[str] = mapped_column(String, nullable=True, default=None)


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String)  # EmailProvider
    email_address: Mapped[str] = mapped_column(String)
    keychain_ref: Mapped[str] = mapped_column(String)  # key name in OS keychain, never the token itself
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="connected")


class ScheduledSource(Base):
    """A folder or connected mailbox the user opted into nightly auto-scanning
    for — the opt-in scheduler (app/scheduler/) only ever touches sources
    with a row here; everything else stays on-demand-only, which is the
    point (off by default, per-source, not sprung on the user)."""

    __tablename__ = "scheduled_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)  # "folder" | "email_account"
    ref: Mapped[str] = mapped_column(String)  # folder path, or EmailAccount.id
    include_subfolders: Mapped[bool] = mapped_column(Boolean, default=True)  # folder kind only
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
