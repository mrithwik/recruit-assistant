"""Basic lifecycle coverage for the in-memory scan-job tracker that lets
/scan/* endpoints return immediately and run the actual scan as a
background task — see app/scanning/job_registry.py."""

import pytest

from app.models.schemas import ScanResult
from app.scanning import job_registry
from app.scanning.job_registry import ScanAlreadyRunningError, complete_job, create_job, fail_job, get_job, update_progress


@pytest.fixture(autouse=True)
def _reset_registry():
    # _jobs/_active_scopes are process-global (see job_registry.py's own
    # docstring on why — mirrors dependencies.py's module-singleton
    # pattern), so tests that reuse a scope key would otherwise collide
    # depending on run order without this reset.
    job_registry._jobs.clear()
    job_registry._active_scopes.clear()
    yield
    job_registry._jobs.clear()
    job_registry._active_scopes.clear()


def test_new_job_starts_running():
    job = create_job()
    assert job.status == "running"
    assert get_job(job.id) is job


def test_complete_job_records_result():
    job = create_job()
    result = ScanResult(resumes_found=3, candidates_created=2, candidates_updated=1)
    complete_job(job.id, result)

    fetched = get_job(job.id)
    assert fetched.status == "completed"
    assert fetched.result == result
    assert fetched.completed_at is not None


def test_fail_job_records_error():
    job = create_job()
    fail_job(job.id, "boom")

    fetched = get_job(job.id)
    assert fetched.status == "failed"
    assert fetched.error == "boom"
    assert fetched.completed_at is not None


def test_unknown_job_returns_none():
    assert get_job("does-not-exist") is None


def test_second_job_for_same_scope_while_running_is_rejected():
    first = create_job("email:acct-1")
    with pytest.raises(ScanAlreadyRunningError) as exc_info:
        create_job("email:acct-1")
    assert exc_info.value.existing_job_id == first.id


def test_different_scopes_can_run_concurrently():
    create_job("email:acct-1")
    other = create_job("email:acct-2")  # different scope — must not raise
    assert other.status == "running"


def test_scope_frees_up_once_job_completes():
    job = create_job("email:acct-1")
    complete_job(job.id, ScanResult(resumes_found=1, candidates_created=1, candidates_updated=0))

    # Same scope, new job — should succeed now that the prior one finished.
    second = create_job("email:acct-1")
    assert second.status == "running"


def test_scope_frees_up_once_job_fails():
    job = create_job("email:acct-1")
    fail_job(job.id, "boom")

    second = create_job("email:acct-1")
    assert second.status == "running"


def test_update_progress_sets_live_counters():
    job = create_job()
    progress = ScanResult(resumes_found=42, candidates_created=10, candidates_updated=5)
    update_progress(job.id, progress)

    assert get_job(job.id).progress == progress


def test_old_finished_jobs_are_pruned_once_over_the_cap():
    for i in range(job_registry.MAX_STORED_JOBS + 5):
        job = create_job(f"scope-{i}")
        complete_job(job.id, ScanResult(resumes_found=1, candidates_created=1, candidates_updated=0))

    assert len(job_registry._jobs) == job_registry.MAX_STORED_JOBS


def test_pruning_never_removes_a_running_job():
    still_running = create_job("scope-running")
    for i in range(job_registry.MAX_STORED_JOBS + 5):
        job = create_job(f"scope-{i}")
        complete_job(job.id, ScanResult(resumes_found=1, candidates_created=1, candidates_updated=0))

    assert get_job(still_running.id) is still_running
