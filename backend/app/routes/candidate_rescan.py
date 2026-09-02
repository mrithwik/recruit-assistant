""""Check this candidate for updates" — a targeted rescan of just the
sources a specific candidate came from, instead of re-scanning an entire
mailbox/folder to catch one person's new submission. The candidate list
gets hard to manage at real volume otherwise: re-running a full mailbox
scan just to check whether one person sent an updated resume is slow and
touches hundreds of unrelated candidates' data for no reason.

Email sources are narrowed with a sender filter (see GmailIngestor/
OutlookIngestor's sender_email) so this stays fast even against a large
mailbox. Folder sources just get re-scanned at whatever folder path they
were originally found in — no per-file narrowing is possible there, but a
single folder is normally small enough that this is still fast.

Any resume this finds merges into the SAME candidate via the existing
identity-resolution/fingerprint matching in ingest_service.py — this route
adds no new merge logic, it just re-points the existing pipeline at a
narrower source.

rescan_candidate_sources() below is reused by routes/match_rescan.py for
the bounded "check just this job's matched candidates" bulk action — same
per-candidate logic, looped, instead of a second implementation."""

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import get_llm_client, get_settings, get_storage
from app.matching.llm_client import LLMClient
from app.models.db import Candidate, EmailAccount, ResumeSource
from app.models.schemas import ScanJobOut, ScanResult
from app.routes.scan import build_email_ingestor, record_ingest_scan, resolve_mock_manifest_path
from app.runtime_settings import get_use_mock_email
from app.scanning.email_ingestor import load_fixtures_from_manifest
from app.scanning.folder_ingestor import FolderIngestor
from app.scanning.ingest_service import run_scan
from app.scanning.job_registry import (
    ScanAlreadyRunningError,
    complete_job,
    create_job,
    fail_job,
    update_progress,
)
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])


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


async def rescan_candidate_sources(
    candidate: Candidate,
    session: Session,
    storage: BaseStorageBackend,
    llm: LLMClient,
    settings: Settings,
    mock_fixtures: list,
    on_progress: Callable[[ScanResult], None] | None = None,
) -> ScanResult:
    """The actual rescan for one candidate — re-scans their known folder
    path(s) as-is, and their known email account(s) filtered to just their
    sender address. Returns the combined ScanResult; raises nothing itself
    (per-account/per-source failures are recorded in the result's errors
    list, matching run_scan's own convention) except if candidate.email is
    blank, which the caller should check before calling this at all."""
    sources = list(session.execute(select(ResumeSource).where(ResumeSource.candidate_id == candidate.id)).scalars())
    folder_paths = sorted({s.source_ref for s in sources if s.origin == "folder"})
    email_accounts = sorted({s.source_ref.split(":", 1)[0] for s in sources if s.origin == "email" and ":" in s.source_ref})

    combined = ScanResult(resumes_found=0, candidates_created=0, candidates_updated=0, duplicates_skipped=0, errors=[])
    if not folder_paths and not email_accounts:
        return combined

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
            max_concurrent_processing=settings.max_concurrent_llm_calls,
            on_progress=on_progress,
        )
        combined.resumes_found += result.resumes_found
        combined.candidates_created += result.candidates_created
        combined.candidates_updated += result.candidates_updated
        combined.duplicates_skipped += result.duplicates_skipped
        combined.errors.extend(result.errors)
        combined.elapsed_seconds += result.elapsed_seconds

    for account_email in email_accounts:
        account = (
            session.execute(select(EmailAccount).where(EmailAccount.email_address == account_email)).scalar_one_or_none()
            if not get_use_mock_email()
            else None
        )
        if not get_use_mock_email() and not account:
            combined.errors.append(f"{account_email}: account not found (disconnected?)")
            continue
        ingestor, error = build_email_ingestor(
            account.id if account else "", account, settings, mock_fixtures, sender_email=candidate.email
        )
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
            max_concurrent_processing=settings.max_concurrent_llm_calls,
            on_progress=on_progress,
        )
        combined.resumes_found += result.resumes_found
        combined.candidates_created += result.candidates_created
        combined.candidates_updated += result.candidates_updated
        combined.duplicates_skipped += result.duplicates_skipped
        combined.errors.extend(result.errors)
        combined.elapsed_seconds += result.elapsed_seconds

    return combined


@router.post("/{candidate_id}/rescan", response_model=ScanJobOut, status_code=202)
async def rescan_candidate(
    candidate_id: str,
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    with storage.session() as session:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            raise HTTPException(404, "Candidate not found")
        if not candidate.email:
            raise HTTPException(400, "This candidate has no email address on file — nothing to scope a rescan to.")

        has_sources = session.execute(
            select(ResumeSource.id).where(ResumeSource.candidate_id == candidate_id).limit(1)
        ).first()
        if not has_sources:
            raise HTTPException(400, "No known source (email or folder) to rescan for this candidate.")

    scope_key = f"candidate_rescan:{candidate_id}"
    try:
        job = create_job(scope_key)
    except ScanAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc

    async def _run() -> None:
        try:
            mock_fixtures = (
                load_fixtures_from_manifest(resolve_mock_manifest_path(settings)) if get_use_mock_email() else []
            )
            with storage.session() as session:
                candidate = session.get(Candidate, candidate_id)
                combined = await rescan_candidate_sources(
                    candidate, session, storage, llm, settings, mock_fixtures, on_progress=lambda r: update_progress(job.id, r)
                )
                record_ingest_scan(storage, session, "email", f"rescan: {candidate.email}", combined)
                session.commit()
            complete_job(job.id, combined)
        except Exception as exc:  # noqa: BLE001 - surfaced via job status, not raised into a dead background task
            fail_job(job.id, str(exc))

    job.task = asyncio.create_task(_run())
    return _job_out(job)
