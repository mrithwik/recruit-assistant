"""In-app sample-data generation (requirement 6) — the same generator behind
scripts/generate_sample_data.py, callable from the UI so a recruiter doesn't
need a terminal to build a test dataset. Runs synchronously; FastAPI's sync
route handling already offloads it to a threadpool so it doesn't block the
event loop, but a large request (thousands of items) can take a while — the
frontend shows a "this may take a minute" hint rather than polling."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, delete, func, select

from app.config import Settings
from app.criteria.service import seed_builtin_criteria
from app.data_classification import is_mock_source_condition
from app.dependencies import _seed_demo_mailbox, get_settings, get_storage
from app.dev_tools.sample_data_generator import generate
from app.models.db import (
    Candidate,
    Criterion,
    EmailAccount,
    Job,
    JobCriterion,
    Match,
    ResumeSource,
    SearchHistoryEntry,
)
from app.models.schemas import (
    ClearDataOut,
    GenerateSampleDataOut,
    GenerateSampleDataRequest,
    SampleSessionDeleteOut,
    SampleSessionOut,
)
from app.runtime_settings import get_use_mock_email
from app.scanning.mirror_writer import delete_candidate_mirror, delete_candidate_mirror_partial
from app.storage.base import BaseStorageBackend

LEGACY_SESSION_ID = "unlabeled-legacy"

router = APIRouter(prefix="/api/v1/dev-tools", tags=["dev-tools"])

MAX_INITIAL = 20_000
MAX_FOLLOWUPS = 6_000
MAX_UPSKILL = 4_000


REPO_ROOT = Path(__file__).resolve().parents[3]


def _default_out_dir(settings: Settings) -> Path:
    # Prefer wherever MOCK_EMAIL_FIXTURES_PATH already points (so a generate
    # click immediately "just works" with the mock email scan without an
    # extra .env edit); otherwise the same sample_data/ the CLI script uses,
    # resolved from this file's location so it doesn't depend on cwd.
    if settings.mock_email_fixtures_path:
        return Path(settings.mock_email_fixtures_path).resolve().parent
    return REPO_ROOT / "sample_data"


@router.post("/generate-sample-data", response_model=GenerateSampleDataOut)
def generate_sample_data(
    payload: GenerateSampleDataRequest,
    settings: Settings = Depends(get_settings),
    storage: BaseStorageBackend = Depends(get_storage),
):
    out_dir = Path(payload.out_dir) if payload.out_dir else _default_out_dir(settings)
    summary = generate(
        out_dir=out_dir,
        seed=payload.seed,
        initial_count=min(payload.initial, MAX_INITIAL),
        followup_count=min(payload.followups, MAX_FOLLOWUPS),
        upskill_count=min(payload.upskill, MAX_UPSKILL),
        label=payload.label,
    )
    if get_use_mock_email():
        # Make the mock mailbox selectable immediately — don't make the
        # recruiter restart the backend just because this was the first
        # generate click and MOCK_EMAIL_FIXTURES_PATH wasn't set yet.
        _seed_demo_mailbox(storage)
    return GenerateSampleDataOut(**summary)


@router.get("/sample-sessions", response_model=list[SampleSessionOut])
def list_sample_sessions(
    settings: Settings = Depends(get_settings),
    storage: BaseStorageBackend = Depends(get_storage),
):
    """Every past 'Generate sample data' run, plus one catch-all bucket for
    mock data ingested before session tagging existed — see
    app/dev_tools/session_tagging.py for how a session id gets stamped onto
    ResumeSource.generation_session_id at scan time. A session only reflects
    what's actually been scanned into the DB (`candidates_scanned`); a
    generated-but-never-scanned batch still shows up (from the manifest)
    with a zero count, so it can still be found and deleted."""
    manifest_path = _default_out_dir(settings) / "emails_manifest.json"
    generated_sessions: list[dict] = []
    if manifest_path.exists():
        try:
            generated_sessions = json.loads(manifest_path.read_text()).get("sessions", [])
        except (OSError, json.JSONDecodeError):
            generated_sessions = []

    with storage.session() as session:
        tagged_counts = dict(
            session.execute(
                select(ResumeSource.generation_session_id, func.count(func.distinct(ResumeSource.candidate_id)))
                .where(ResumeSource.generation_session_id.is_not(None))
                .group_by(ResumeSource.generation_session_id)
            ).all()
        )
        legacy_count = session.execute(
            select(func.count(func.distinct(ResumeSource.candidate_id))).where(
                is_mock_source_condition(), ResumeSource.generation_session_id.is_(None)
            )
        ).scalar_one()

    results = [
        SampleSessionOut(
            id=s["id"],
            label=s.get("label") or s["id"],
            generated_at=s.get("generated_at", ""),
            seed=s.get("seed"),
            total_items=s.get("total_items", 0),
            candidates_scanned=tagged_counts.get(s["id"], 0),
            scanned=tagged_counts.get(s["id"], 0) > 0,
        )
        for s in generated_sessions
    ]
    if legacy_count:
        results.append(
            SampleSessionOut(
                id=LEGACY_SESSION_ID,
                label="Unlabeled (before session tracking)",
                generated_at="",
                seed=None,
                total_items=legacy_count,
                candidates_scanned=legacy_count,
                scanned=True,
            )
        )
    results.sort(key=lambda r: r.generated_at, reverse=True)
    return results


def _delete_session_files(out_dir: Path, session_id: str) -> bool:
    """Removes any not-yet-scanned raw files this session wrote (resumes/
    and attachments/ trees), plus its manifest entry, so a deleted session
    can't be accidentally re-scanned later. Never touches another session's
    files — every filename this session wrote carries its session id as a
    prefix (see session_tagging.tag_filename)."""
    manifest_path = out_dir / "emails_manifest.json"
    deleted_any = False

    for base_dir in (out_dir / "resumes", out_dir / "attachments"):
        if not base_dir.exists():
            continue
        for path in base_dir.rglob(f"{session_id}__*"):
            if path.is_file():
                path.unlink(missing_ok=True)
                deleted_any = True

    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            return deleted_any
        remaining_sessions = [s for s in data.get("sessions", []) if s.get("id") != session_id]
        remaining_emails = [e for e in data.get("emails", []) if e.get("session_id") != session_id]
        if len(remaining_sessions) != len(data.get("sessions", [])) or len(remaining_emails) != len(
            data.get("emails", [])
        ):
            data["sessions"] = remaining_sessions
            data["emails"] = remaining_emails
            data["count"] = len(remaining_emails)
            manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            deleted_any = True
    return deleted_any


@router.delete("/sample-sessions/{session_id}", response_model=SampleSessionDeleteOut)
def delete_sample_session(
    session_id: str,
    settings: Settings = Depends(get_settings),
    storage: BaseStorageBackend = Depends(get_storage),
):
    """Deletes one generation session's worth of candidates — a real,
    irreversible delete (mirror files + DB rows), the same pattern as
    routes/candidates.py's per-candidate delete, just applied to every
    candidate this session touched. A candidate whose *only* sources came
    from this session is deleted outright; a candidate that also has
    sources from another session or from real data (e.g. the same synthetic
    person regenerated under a different seed) is trimmed — just this
    session's sources and files are removed, the candidate itself stays."""
    with storage.session() as session:
        if session_id == LEGACY_SESSION_ID:
            condition = and_(is_mock_source_condition(), ResumeSource.generation_session_id.is_(None))
        else:
            condition = ResumeSource.generation_session_id == session_id

        matching_sources = list(session.execute(select(ResumeSource).where(condition)).scalars())

        by_candidate: dict[str, list[ResumeSource]] = {}
        for src in matching_sources:
            by_candidate.setdefault(src.candidate_id, []).append(src)

        candidates_deleted = 0
        candidates_trimmed = 0
        sources_deleted = 0
        for candidate_id, sources_in_session in by_candidate.items():
            candidate = session.get(Candidate, candidate_id)
            if candidate is None:
                continue
            all_sources = list(
                session.execute(select(ResumeSource).where(ResumeSource.candidate_id == candidate_id)).scalars()
            )
            if len(sources_in_session) == len(all_sources):
                delete_candidate_mirror(candidate_id, all_sources)
                session.delete(candidate)
                candidates_deleted += 1
            else:
                surviving_sources = [s for s in all_sources if s not in sources_in_session]
                delete_candidate_mirror_partial(candidate_id, sources_in_session, surviving_sources)
                for src in sources_in_session:
                    session.delete(src)
                candidates_trimmed += 1
            sources_deleted += len(sources_in_session)
        session.commit()

    # A batch that was generated but never scanned has no ResumeSource rows
    # yet — that's not "not found", it just means there's nothing in the DB
    # to touch. list_sample_sessions surfaces exactly this case (see its
    # docstring), so it must be deletable here too: only 404 when there was
    # neither a DB match nor any on-disk trace to clean up.
    files_deleted = False
    if session_id != LEGACY_SESSION_ID:
        files_deleted = _delete_session_files(_default_out_dir(settings), session_id)

    if not matching_sources and not files_deleted:
        raise HTTPException(404, "Sample session not found or already empty")

    return SampleSessionDeleteOut(
        candidates_deleted=candidates_deleted,
        candidates_trimmed=candidates_trimmed,
        sources_deleted=sources_deleted,
        files_deleted=files_deleted,
    )


@router.post("/clear-data", response_model=ClearDataOut)
def clear_data(storage: BaseStorageBackend = Depends(get_storage)):
    """Wipes every job/candidate/match/criteria/email-account row — the
    'clear if needed' counterpart to sample-data generation, so testing
    across code changes doesn't force a regenerate-from-scratch cycle
    unless the recruiter actually wants a clean slate. The local user
    account and generated files on disk (sample_data/, data/candidates/)
    are left untouched — this only clears the database."""
    with storage.session() as session:
        jobs_deleted = session.execute(select(func.count()).select_from(Job)).scalar_one()
        candidates_deleted = session.execute(select(func.count()).select_from(Candidate)).scalar_one()
        matches_deleted = session.execute(select(func.count()).select_from(Match)).scalar_one()
        criteria_deleted = session.execute(select(func.count()).select_from(Criterion)).scalar_one()
        email_accounts_deleted = session.execute(select(func.count()).select_from(EmailAccount)).scalar_one()

        # Children before parents (SQLite here doesn't enforce FKs, but
        # keeping the order correct in case that ever changes).
        session.execute(delete(Match))
        session.execute(delete(JobCriterion))
        session.execute(delete(ResumeSource))
        session.execute(delete(SearchHistoryEntry))
        session.execute(delete(Candidate))
        session.execute(delete(Job))
        session.execute(delete(Criterion))
        session.execute(delete(EmailAccount))
        session.commit()

        # Re-seed the criteria library so it isn't empty afterward — it's a
        # global library, not scan/candidate data, so it should survive a
        # "clear my test data" action conceptually even though the rows
        # were just deleted for simplicity above.
        seed_builtin_criteria(session)

    return ClearDataOut(
        jobs_deleted=jobs_deleted,
        candidates_deleted=candidates_deleted,
        matches_deleted=matches_deleted,
        criteria_deleted=criteria_deleted,
        email_accounts_deleted=email_accounts_deleted,
    )
