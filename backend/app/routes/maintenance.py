"""Data-maintenance tasks (see app/maintenance/tasks.py for what this is and
why) — runs one registered task as a background job and lets the frontend
poll it exactly like a scan, reusing job_registry.py wholesale rather than
building a second job-tracking system with the same shape."""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.dependencies import get_settings, get_storage
from app.maintenance.tasks import TASKS
from app.models.db import IngestScanHistoryEntry
from app.models.schemas import MaintenanceTaskOut, ScanJobOut
from app.scanning.job_registry import (
    ScanAlreadyRunningError,
    complete_job,
    create_job,
    fail_job,
    get_job,
    is_cancel_requested,
    update_progress,
)
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/maintenance", tags=["maintenance"])


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


@router.get("/tasks", response_model=list[MaintenanceTaskOut])
def list_tasks(storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        return [
            MaintenanceTaskOut(id=t.id, label=t.label, description=t.description, pending_count=t.pending_count(session))
            for t in TASKS.values()
        ]


@router.post("/tasks/{task_id}/run", response_model=ScanJobOut, status_code=202)
async def run_task(
    task_id: str,
    storage: BaseStorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, f"Unknown maintenance task: {task_id}")

    try:
        job = create_job(scope_key=f"maintenance:{task_id}")
    except ScanAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc

    async def _run() -> None:
        try:
            with storage.session() as session:
                result = await task.run(
                    session, settings, lambda r: update_progress(job.id, r), lambda: is_cancel_requested(job.id)
                )
                # Same Recent Activity feed as scans (see IngestScanHistoryEntry)
                # so a maintenance run isn't invisible outside this one page —
                # origin="maintenance" branches to different wording in
                # dashboard/service.py's _recent_activity.
                storage.record_ingest_scan(
                    session,
                    IngestScanHistoryEntry(
                        id=str(uuid.uuid4()),
                        origin="maintenance",
                        source_label=task.label,
                        resumes_found=result.resumes_found,
                        candidates_created=result.candidates_created,
                        candidates_updated=result.candidates_updated,
                        duplicates_skipped=result.duplicates_skipped,
                        error_count=len(result.errors),
                    ),
                )
                session.commit()
            complete_job(job.id, result)
        except Exception as exc:  # noqa: BLE001 - surfaced via job status, not raised into a dead background task
            fail_job(job.id, str(exc))

    job.task = asyncio.create_task(_run())
    return _job_out(job)
