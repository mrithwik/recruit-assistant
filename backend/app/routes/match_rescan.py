""""Check for updates" on Match Results, scoped to just this job's already-
matched candidates — the bounded, fast option compared to All Candidates'
"Rescan all" (which is one full mailbox/folder pass): a job's match list is
naturally capped (topN, default 20, max 200), so looping the per-candidate
scoped rescan (routes/candidate_rescan.py) over just that list is cheap and
gives a precise "N of these M candidates actually had something new"
answer, which a bulk mailbox scan can't (it can't tell you which of your
matched candidates specifically changed)."""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.config import Settings
from app.dependencies import get_llm_client, get_settings, get_storage
from app.matching.llm_client import LLMClient
from app.models.db import Candidate, IngestScanHistoryEntry, Job, Match
from app.models.schemas import ScanJobOut, ScanResult
from app.routes.candidate_rescan import rescan_candidate_sources
from app.routes.scan import resolve_mock_manifest_path
from app.runtime_settings import get_use_mock_email
from app.scanning.email_ingestor import load_fixtures_from_manifest
from app.scanning.job_registry import (
    ScanAlreadyRunningError,
    complete_job,
    create_job,
    fail_job,
    update_progress,
)
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


def _job_out(job) -> ScanJobOut:
    return ScanJobOut(
        id=job.id,
        status=job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result=job.result,
        progress=job.progress,
        error=job.error,
    )


@router.post("/{job_id}/rescan-matched", response_model=ScanJobOut, status_code=202)
async def rescan_matched_candidates(
    job_id: str,
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    with storage.session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        candidate_ids = list(
            session.execute(select(Match.candidate_id).where(Match.job_id == job_id).distinct()).scalars()
        )
        job_title = job.title

    if not candidate_ids:
        raise HTTPException(400, "No matches yet for this job — run matching first.")

    scope_key = f"rescan_matched:{job_id}"
    try:
        rjob = create_job(scope_key)
    except ScanAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc

    async def _run() -> None:
        checked = 0
        updated = 0
        errors: list[str] = []
        try:
            mock_fixtures = (
                load_fixtures_from_manifest(resolve_mock_manifest_path(settings)) if get_use_mock_email() else []
            )
            with storage.session() as session:
                for candidate_id in candidate_ids:
                    candidate = session.get(Candidate, candidate_id)
                    checked += 1
                    if not candidate or not candidate.email:
                        continue
                    result = await rescan_candidate_sources(candidate, session, storage, llm, settings, mock_fixtures)
                    if result.candidates_updated > 0:
                        updated += 1
                    errors.extend(result.errors)
                    update_progress(
                        rjob.id,
                        ScanResult(
                            resumes_found=checked,
                            candidates_created=0,
                            candidates_updated=updated,
                            duplicates_skipped=checked - updated,
                            errors=errors,
                        ),
                    )

                final = ScanResult(
                    resumes_found=checked,
                    candidates_created=0,
                    candidates_updated=updated,
                    duplicates_skipped=checked - updated,
                    errors=errors,
                )
                storage.record_ingest_scan(
                    session,
                    IngestScanHistoryEntry(
                        id=str(uuid.uuid4()),
                        origin="email",
                        source_label=f"rescan matched: {job_title}",
                        resumes_found=final.resumes_found,
                        candidates_created=final.candidates_created,
                        candidates_updated=final.candidates_updated,
                        duplicates_skipped=final.duplicates_skipped,
                        error_count=len(final.errors),
                    ),
                )
            complete_job(rjob.id, final)
        except Exception as exc:  # noqa: BLE001 - surfaced via job status, not raised into a dead background task
            fail_job(rjob.id, str(exc))

    rjob.task = asyncio.create_task(_run())
    return _job_out(rjob)
