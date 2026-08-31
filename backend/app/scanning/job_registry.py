"""In-memory scan-job tracker. /scan/folders and /scan/email-accounts used to
block the HTTP request for the entire scan — fine for a folder scan or a
mock-fixture scan, but a real Gmail/Outlook scan at real-mailbox scale can
run for tens of minutes even with the concurrency fixes in email_ingestor.py,
and holding one HTTP request open that long is bad UX (no progress, and
real risk of a browser/proxy timing out the connection). Instead the route
kicks off the scan as a background asyncio task and returns immediately;
the frontend polls GET /scan/jobs/{id} for status/live progress/result.

Job state is intentionally in-memory only, not persisted — a backend
restart mid-scan already killed the running task, so a persisted "running"
row would be stale/misleading, not useful. Same module-global pattern as
app/dependencies.py (ADR-008: simple, explicit, testable)."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.models.schemas import ScanResult

JobStatus = Literal["running", "completed", "failed"]


class ScanAlreadyRunningError(Exception):
    """Raised by create_job() when a scan is already running for the same
    scope (same account_ids, or same folder_paths) — closes a real gap: the
    "scanning" button-disable state lives in browser JS and isn't persisted,
    so a page refresh mid-scan resets it, and re-clicking would otherwise
    start a second overlapping job with no visibility into the first one's
    in-flight work (each job preloads its own dedup cache at start, so two
    overlapping jobs can't see each other's new candidates — real risk of
    duplicates)."""

    def __init__(self, existing_job_id: str):
        super().__init__(f"A scan is already running for this scope (job {existing_job_id}).")
        self.existing_job_id = existing_job_id


@dataclass
class ScanJob:
    id: str
    scope_key: str = ""
    status: JobStatus = "running"
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    result: ScanResult | None = None
    # Live counters while status == "running" — see run_scan's on_progress.
    progress: ScanResult | None = None
    error: str | None = None
    # Holds the asyncio.Task itself — required so it isn't garbage-collected
    # mid-run (a bare `asyncio.create_task(...)` with no kept reference is a
    # classic asyncio footgun: nothing stops the GC from reclaiming it).
    task: Any = None


_jobs: dict[str, ScanJob] = {}
_active_scopes: dict[str, str] = {}  # scope_key -> job_id, only while running

# Nothing ever prunes this dict otherwise — harmless over one session, but
# an app left open for months would slowly accumulate every scan ever run.
# Only completed/failed jobs are ever evicted; a running one is never
# touched regardless of how old it is.
MAX_STORED_JOBS = 50


def _prune() -> None:
    if len(_jobs) <= MAX_STORED_JOBS:
        return
    finished = sorted(
        (j for j in _jobs.values() if j.status != "running"),
        key=lambda j: j.completed_at or j.started_at,
    )
    for job in finished[: len(_jobs) - MAX_STORED_JOBS]:
        del _jobs[job.id]


def create_job(scope_key: str = "") -> ScanJob:
    if scope_key and scope_key in _active_scopes:
        existing_id = _active_scopes[scope_key]
        existing = _jobs.get(existing_id)
        if existing and existing.status == "running":
            raise ScanAlreadyRunningError(existing_id)

    job = ScanJob(id=str(uuid.uuid4()), scope_key=scope_key)
    _jobs[job.id] = job
    if scope_key:
        _active_scopes[scope_key] = job.id
    return job


def get_job(job_id: str) -> ScanJob | None:
    return _jobs.get(job_id)


def update_progress(job_id: str, progress: ScanResult) -> None:
    job = _jobs.get(job_id)
    if job:
        job.progress = progress


def complete_job(job_id: str, result: ScanResult) -> None:
    job = _jobs[job_id]
    job.status = "completed"
    job.result = result
    job.completed_at = datetime.utcnow()
    if job.scope_key and _active_scopes.get(job.scope_key) == job_id:
        del _active_scopes[job.scope_key]
    _prune()


def fail_job(job_id: str, error: str) -> None:
    job = _jobs[job_id]
    job.status = "failed"
    job.error = error
    job.completed_at = datetime.utcnow()
    if job.scope_key and _active_scopes.get(job.scope_key) == job_id:
        del _active_scopes[job.scope_key]
    _prune()
