"""In-app sample-data generation (requirement 6) — the same generator behind
scripts/generate_sample_data.py, callable from the UI so a recruiter doesn't
need a terminal to build a test dataset. Runs synchronously; FastAPI's sync
route handling already offloads it to a threadpool so it doesn't block the
event loop, but a large request (thousands of items) can take a while — the
frontend shows a "this may take a minute" hint rather than polling."""

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select

from app.config import Settings
from app.criteria.service import seed_builtin_criteria
from app.dependencies import _seed_demo_mailbox, get_settings, get_storage
from app.dev_tools.sample_data_generator import generate
from app.models.db import Candidate, Criterion, EmailAccount, Job, JobCriterion, Match, ResumeSource, SearchHistoryEntry
from app.models.schemas import ClearDataOut, GenerateSampleDataOut, GenerateSampleDataRequest
from app.storage.base import BaseStorageBackend

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
    )
    if settings.use_mock:
        # Make the mock mailbox selectable immediately — don't make the
        # recruiter restart the backend just because this was the first
        # generate click and MOCK_EMAIL_FIXTURES_PATH wasn't set yet.
        _seed_demo_mailbox(storage)
    return GenerateSampleDataOut(**summary)


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
