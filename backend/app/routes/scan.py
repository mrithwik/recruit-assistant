"""Scan Sources tab (2.2) — folder scan and email scan, both converging on
run_scan(). Both are first-class: a recruiter with no local resumes yet can
scan email alone, or a recruiter with only saved folders can skip email.

Both POST endpoints kick the scan off as a background asyncio task and
return a job id immediately (202) instead of blocking the request until the
scan finishes — see app/scanning/job_registry.py for why (a real email scan
can run long enough that holding one HTTP request open for it is bad UX and
risks a timeout). Poll GET /scan/jobs/{id} for live progress/result. A
second scan for the same scope (same account_ids / same folder_paths)
while one is already running is rejected (409) rather than silently
racing two overlapping jobs — see ScanAlreadyRunningError."""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.config import Settings
from app.dependencies import get_llm_client, get_settings, get_storage
from app.email_auth.oauth import get_valid_access_token
from app.matching.llm_client import LLMClient
from app.models.db import EmailAccount, IngestScanHistoryEntry, ResumeSource
from app.models.schemas import (
    IngestScanLogOut,
    ScanEmailRequest,
    ScanFolderRequest,
    ScanJobOut,
    ScanResult,
)
from app.runtime_settings import get_use_mock_email
from app.scanning.email_ingestor import (
    GmailIngestor,
    MockEmailIngestor,
    OutlookIngestor,
    load_fixtures_from_manifest,
)
from app.scanning.folder_ingestor import FolderIngestor
from app.scanning.ingest_service import run_scan
from app.scanning.job_registry import (
    ScanAlreadyRunningError,
    complete_job,
    create_job,
    fail_job,
    get_job,
    is_cancel_requested,
    request_cancel,
    update_progress,
)
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/scan", tags=["scan"])

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MOCK_MANIFEST = REPO_ROOT / "sample_data" / "emails_manifest.json"


def resolve_mock_manifest_path(settings: Settings) -> str:
    # MOCK_EMAIL_FIXTURES_PATH may not be set yet on a fresh install — the
    # in-app generator (dev_tools.py) writes to sample_data/ by default
    # regardless, so fall back to that path rather than silently scanning
    # nothing (see project-log: "generated data not showing up" bug).
    if settings.mock_email_fixtures_path:
        return settings.mock_email_fixtures_path
    return str(DEFAULT_MOCK_MANIFEST)


def build_email_ingestor(
    account_id: str, account: EmailAccount, settings: Settings, mock_fixtures: list, sender_email: str = ""
) -> tuple[object | None, str | None]:
    """Shared by the on-demand /email-accounts route, the opt-in scheduler's
    nightly job, and the per-candidate rescan route — one place that decides
    mock vs. real, and real-Gmail vs. real-Outlook, so callers can't drift.
    Returns (ingestor, error_message); exactly one is non-None. sender_email,
    when set, narrows the scan to just that person's messages (see
    routes/candidate_rescan.py)."""
    if get_use_mock_email():
        return MockEmailIngestor(fixtures=mock_fixtures, sender_email=sender_email), None

    access_token = get_valid_access_token(
        account_id,
        account.provider,
        ms_client_id=settings.ms_oauth_client_id,
        ms_client_secret=settings.ms_oauth_client_secret,
        ms_tenant_id=settings.ms_oauth_tenant_id,
    )
    if not access_token:
        return None, f"{account_id}: no stored token, reconnect the account"
    if account.provider == "gmail":
        return (
            GmailIngestor(access_token, account.email_address, max_concurrent=settings.max_concurrent_email_fetches, sender_email=sender_email),
            None,
        )
    return (
        OutlookIngestor(access_token, account.email_address, max_concurrent=settings.max_concurrent_email_fetches, sender_email=sender_email),
        None,
    )


def record_ingest_scan(storage: BaseStorageBackend, session, origin: str, source_label: str, result: ScanResult) -> None:
    # One row per completed scan (regardless of resumes_found — a scan
    # that found nothing new is still worth showing on the dashboard, e.g.
    # "Scanned Gmail — 0 new" confirms the scan ran rather than looking like
    # nothing happened) — see IngestScanHistoryEntry's docstring for why
    # this exists separately from SearchHistoryEntry.
    storage.record_ingest_scan(
        session,
        IngestScanHistoryEntry(
            id=str(uuid.uuid4()),
            origin=origin,
            source_label=source_label,
            resumes_found=result.resumes_found,
            candidates_created=result.candidates_created,
            candidates_updated=result.candidates_updated,
            duplicates_skipped=result.duplicates_skipped,
            error_count=len(result.errors),
        ),
    )


def _merge_stage_timings(*timings: dict[str, float]) -> dict[str, float]:
    """Sums per-stage seconds across multiple ScanResults — used wherever a
    route loops over several sources (accounts, folders) and combines their
    individual run_scan() results into one, so ScanResult.stage_timings
    doesn't get silently dropped the way the other accumulated fields
    aren't (see QA finding on the scan-instrumentation work: combined only
    summed resumes_found/candidates_created/etc., never stage_timings).

    Deliberately unrounded: each input dict is already unrounded (run_scan
    stopped rounding its own stage_timings for exactly this reason), and
    summing already-rounded per-call numbers can quantize real-but-small
    work down to a false 0.00 that then propagates through every further
    merge (see QA finding — a two-account scan where each account's real
    parse time individually rounded to 0.00 summed to a 0.00 total that hid
    real, confirmed-happened work). Round once, at the point the result is
    finally handed to a job as its displayed state — see
    _round_stage_timings."""
    merged: dict[str, float] = {}
    for t in timings:
        for key, value in t.items():
            merged[key] = merged.get(key, 0.0) + value
    return merged


def _round_stage_timings(timings: dict[str, float]) -> dict[str, float]:
    """Rounds stage_timings for display — call this exactly once, at the
    point a ScanResult is handed to complete_job/update_progress as a job's
    outward-facing state, never before or in between accumulation steps.
    See _merge_stage_timings for why early rounding is wrong."""
    return {k: round(v, 2) for k, v in timings.items()}


def _job_out(job) -> ScanJobOut:
    return ScanJobOut(
        id=job.id,
        status=job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result=job.result,
        progress=job.progress,
        error=job.error,
        cancelled=job.cancelled,
    )


@router.post("/folders", response_model=ScanJobOut, status_code=202)
async def scan_folders(
    payload: ScanFolderRequest,
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    scope_key = "folders:" + "|".join(sorted(payload.folder_paths))
    try:
        job = create_job(scope_key)
    except ScanAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc

    async def _run() -> None:
        try:
            ingestor = FolderIngestor(payload.folder_paths, include_subfolders=payload.include_subfolders)
            with storage.session() as session:
                result = await run_scan(
                    ingestor=ingestor,
                    storage=storage,
                    session=session,
                    candidates_dir=settings.candidates_dir,
                    llm=llm,
                    summary_model=settings.llm_scoring_model,
                    embedding_model=settings.embedding_model,
                    date_start=payload.date_start,
                    date_end=payload.date_end,
                    max_concurrent_embeddings=settings.max_concurrent_llm_calls,
                    on_progress=lambda r: update_progress(job.id, r),
                    on_should_cancel=lambda: is_cancel_requested(job.id),
                )
                record_ingest_scan(storage, session, "folder", ", ".join(payload.folder_paths), result)
                session.commit()
            result.stage_timings = _round_stage_timings(result.stage_timings)
            complete_job(job.id, result)
        except Exception as exc:  # noqa: BLE001 - surfaced via job status, not raised into a dead background task
            fail_job(job.id, str(exc))

    job.task = asyncio.create_task(_run())
    return _job_out(job)


@router.post("/email-accounts", response_model=ScanJobOut, status_code=202)
async def scan_email_accounts(
    payload: ScanEmailRequest,
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    if not payload.account_ids:
        raise HTTPException(400, "No email accounts specified.")

    scope_key = "email:" + "|".join(sorted(payload.account_ids))
    try:
        job = create_job(scope_key)
    except ScanAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc

    async def _run() -> None:
        combined = ScanResult(resumes_found=0, candidates_created=0, candidates_updated=0, duplicates_skipped=0, errors=[])
        account_labels: list[str] = []
        try:
            mock_fixtures = (
                load_fixtures_from_manifest(resolve_mock_manifest_path(settings)) if get_use_mock_email() else []
            )
            with storage.session() as session:
                for account_id in payload.account_ids:
                    if is_cancel_requested(job.id):
                        break
                    # Looked up regardless of mock/real mode (matching the
                    # scheduler's nightly job) — under mock, build_email_ingestor
                    # never touches `account`, but the caller still needs it
                    # to write last_scanned_at back below. The old
                    # mock-mode-skips-the-lookup version was why a mock scan
                    # of a real connected account (e.g. the dev-seeded
                    # "demo@mock.local" row) never updated its record.
                    account = session.get(EmailAccount, account_id)
                    if not get_use_mock_email() and not account:
                        combined.errors.append(f"{account_id}: account not found")
                        continue
                    ingestor, error = build_email_ingestor(account_id, account, settings, mock_fixtures)
                    if error:
                        combined.errors.append(error)
                        continue
                    account_labels.append(account.email_address if account else "mock mailbox")

                    # Live progress must reflect the grand total across
                    # already-completed accounts plus this account's partial
                    # progress so far — captures `combined`'s state at the
                    # start of this account, since `combined` itself only
                    # gets updated once this account's run_scan returns.
                    base_resumes_found = combined.resumes_found
                    base_created = combined.candidates_created
                    base_updated = combined.candidates_updated
                    base_skipped = combined.duplicates_skipped
                    base_stage_timings = dict(combined.stage_timings)

                    def _on_progress(
                        partial: ScanResult,
                        _resumes_found=base_resumes_found,
                        _created=base_created,
                        _updated=base_updated,
                        _skipped=base_skipped,
                        _stage_timings=base_stage_timings,
                    ) -> None:
                        # Bound as default-arg values (not read from the
                        # enclosing scope) so this closure can't accidentally
                        # pick up a later loop iteration's reassigned
                        # base_* — see ruff B023.
                        update_progress(
                            job.id,
                            ScanResult(
                                resumes_found=_resumes_found + partial.resumes_found,
                                candidates_created=_created + partial.candidates_created,
                                candidates_updated=_updated + partial.candidates_updated,
                                duplicates_skipped=_skipped + partial.duplicates_skipped,
                                errors=combined.errors + partial.errors,
                                elapsed_seconds=partial.elapsed_seconds,
                                stage_timings=_round_stage_timings(
                                    _merge_stage_timings(_stage_timings, partial.stage_timings)
                                ),
                            ),
                        )

                    result = await run_scan(
                        ingestor=ingestor,
                        storage=storage,
                        session=session,
                        candidates_dir=settings.candidates_dir,
                        llm=llm,
                        summary_model=settings.llm_scoring_model,
                        embedding_model=settings.embedding_model,
                        date_start=payload.date_start,
                        date_end=payload.date_end,
                        max_concurrent_embeddings=settings.max_concurrent_llm_calls,
                        on_progress=_on_progress,
                        on_should_cancel=lambda: is_cancel_requested(job.id),
                    )
                    if account:
                        # Tracked (SearchHistoryEntry/IngestScanHistoryEntry)
                        # but never written back to the account record
                        # itself — the Email Access page reads this field
                        # directly and had no way to reflect a scan that
                        # just happened.
                        account.last_scanned_at = datetime.utcnow()
                    combined.resumes_found += result.resumes_found
                    combined.candidates_created += result.candidates_created
                    combined.candidates_updated += result.candidates_updated
                    combined.duplicates_skipped += result.duplicates_skipped
                    combined.errors.extend(result.errors)
                    combined.elapsed_seconds = round(combined.elapsed_seconds + result.elapsed_seconds, 2)
                    combined.stage_timings = _merge_stage_timings(combined.stage_timings, result.stage_timings)
                record_ingest_scan(storage, session, "email", ", ".join(account_labels), combined)
                session.commit()
            combined.stage_timings = _round_stage_timings(combined.stage_timings)
            complete_job(job.id, combined)
        except Exception as exc:  # noqa: BLE001 - surfaced via job status, not raised into a dead background task
            fail_job(job.id, str(exc))

    job.task = asyncio.create_task(_run())
    return _job_out(job)


@router.post("/all", response_model=ScanJobOut, status_code=202)
async def scan_all(
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    """"Rescan all for updates" on the All Candidates page — one combined
    pass over every connected email account plus every folder path already
    known from existing candidates, so a recruiter doesn't have to
    remember/re-enter sources on the Scan Sources page just to check
    whether anything's new. Deliberately one bulk pass (same cost as a
    normal Scan Sources run) rather than looping a per-candidate scoped
    rescan across the whole pool — at real volume (hundreds of candidates)
    that would mean hundreds of separate mailbox searches instead of one."""
    with storage.session() as session:
        account_ids = list(session.execute(select(EmailAccount.id)).scalars())
        folder_paths = sorted(
            set(session.execute(select(ResumeSource.source_ref).where(ResumeSource.origin == "folder")).scalars())
        )

    if not account_ids and not folder_paths:
        raise HTTPException(400, "No connected accounts or known folders to rescan yet.")

    try:
        job = create_job(scope_key="all")
    except ScanAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc

    async def _run() -> None:
        combined = ScanResult(resumes_found=0, candidates_created=0, candidates_updated=0, duplicates_skipped=0, errors=[])
        try:
            mock_fixtures = (
                load_fixtures_from_manifest(resolve_mock_manifest_path(settings)) if get_use_mock_email() else []
            )
            with storage.session() as session:
                if folder_paths:
                    result = await run_scan(
                        ingestor=FolderIngestor(folder_paths, include_subfolders=False),
                        storage=storage,
                        session=session,
                        candidates_dir=settings.candidates_dir,
                        llm=llm,
                        summary_model=settings.llm_scoring_model,
                        embedding_model=settings.embedding_model,
                        max_concurrent_embeddings=settings.max_concurrent_llm_calls,
                        on_progress=lambda r: update_progress(job.id, r),
                        on_should_cancel=lambda: is_cancel_requested(job.id),
                    )
                    combined.resumes_found += result.resumes_found
                    combined.candidates_created += result.candidates_created
                    combined.candidates_updated += result.candidates_updated
                    combined.duplicates_skipped += result.duplicates_skipped
                    combined.errors.extend(result.errors)
                    combined.elapsed_seconds += result.elapsed_seconds
                    combined.stage_timings = _merge_stage_timings(combined.stage_timings, result.stage_timings)

                for account_id in account_ids:
                    if is_cancel_requested(job.id):
                        break
                    # See scan_email_accounts above — looked up regardless
                    # of mock/real mode so last_scanned_at still gets
                    # written for a mock scan of a real account row.
                    account = session.get(EmailAccount, account_id)
                    if not get_use_mock_email() and not account:
                        combined.errors.append(f"{account_id}: account not found")
                        continue
                    ingestor, error = build_email_ingestor(account_id, account, settings, mock_fixtures)
                    if error:
                        combined.errors.append(error)
                        continue
                    result = await run_scan(
                        ingestor=ingestor,
                        storage=storage,
                        session=session,
                        candidates_dir=settings.candidates_dir,
                        llm=llm,
                        summary_model=settings.llm_scoring_model,
                        embedding_model=settings.embedding_model,
                        max_concurrent_embeddings=settings.max_concurrent_llm_calls,
                        on_progress=lambda r: update_progress(job.id, r),
                        on_should_cancel=lambda: is_cancel_requested(job.id),
                    )
                    if account:
                        account.last_scanned_at = datetime.utcnow()
                    combined.resumes_found += result.resumes_found
                    combined.candidates_created += result.candidates_created
                    combined.candidates_updated += result.candidates_updated
                    combined.duplicates_skipped += result.duplicates_skipped
                    combined.errors.extend(result.errors)
                    combined.elapsed_seconds += result.elapsed_seconds
                    combined.stage_timings = _merge_stage_timings(combined.stage_timings, result.stage_timings)

                record_ingest_scan(storage, session, "email" if account_ids else "folder", "rescan all", combined)
                session.commit()
            combined.stage_timings = _round_stage_timings(combined.stage_timings)
            complete_job(job.id, combined)
        except Exception as exc:  # noqa: BLE001 - surfaced via job status, not raised into a dead background task
            fail_job(job.id, str(exc))

    job.task = asyncio.create_task(_run())
    return _job_out(job)


@router.get("/logs", response_model=list[IngestScanLogOut])
def list_scan_logs(storage: BaseStorageBackend = Depends(get_storage)):
    """Every completed scan/rescan/maintenance run, most recent first — a
    detailed record for monitoring purposes (what ran, what source, what it
    found), distinct from Recent Activity on the Dashboard (which summarizes
    and truncates for a quick glance). See scan-page.tsx's "View scan
    activity log" link."""
    with storage.session() as session:
        stmt = select(IngestScanHistoryEntry).order_by(IngestScanHistoryEntry.ran_at.desc())
        return list(session.execute(stmt).scalars())


@router.get("/jobs/{job_id}", response_model=ScanJobOut)
async def get_scan_job(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Scan job not found.")
    return _job_out(job)


@router.post("/jobs/{job_id}/cancel", response_model=ScanJobOut, status_code=202)
async def cancel_scan_job(job_id: str):
    """Generic cancel for any job_registry-backed job — scans, rescans,
    matching runs, maintenance tasks all share the same registry, so one
    route works for all of them (mirroring GET /scan/jobs/{id} above).
    Cooperative: marks the job so its own loop stops at its next checkpoint
    and keeps whatever it already found/saved rather than discarding it —
    see job_registry.request_cancel for why "discard everything" isn't
    what this does."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Scan job not found.")
    request_cancel(job_id)
    return _job_out(get_job(job_id))
