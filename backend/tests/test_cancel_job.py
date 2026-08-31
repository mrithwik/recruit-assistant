"""Cancel support for any job_registry-backed job (scans, rescans, matching
runs) — "stop and keep whatever progress was already made" per the scope
decided for this feature (not a full discard/rollback, see
job_registry.request_cancel's docstring). Timing-based "cancel mid-scan and
assert it actually stopped early" would be flaky against a fast local mock
scan (no reliable way to pause it mid-flight in a test), so this pins the
deterministic parts: the registry primitive itself, and the route's
behavior against jobs that aren't (or are no longer) running."""

import pytest
from fastapi.testclient import TestClient

from app.scanning.job_registry import complete_job, create_job, is_cancel_requested, request_cancel
from app.models.schemas import ScanResult


def test_request_cancel_marks_a_running_job():
    job = create_job()
    assert is_cancel_requested(job.id) is False

    assert request_cancel(job.id) is True
    assert is_cancel_requested(job.id) is True


def test_request_cancel_on_unknown_job_returns_false():
    assert request_cancel("no-such-job") is False


def test_request_cancel_on_finished_job_returns_false():
    job = create_job()
    complete_job(job.id, ScanResult(resumes_found=1, candidates_created=1, candidates_updated=0, duplicates_skipped=0))
    assert request_cancel(job.id) is False


def test_complete_job_records_cancelled_flag_when_requested():
    job = create_job()
    request_cancel(job.id)
    complete_job(job.id, ScanResult(resumes_found=3, candidates_created=2, candidates_updated=0, duplicates_skipped=1))
    assert job.status == "completed"
    assert job.cancelled is True
    # Whatever was found before cancelling is real, saved progress — not
    # wiped just because the run stopped early.
    assert job.result.candidates_created == 2


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_EMAIL", "true")

    from app.dependencies import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def _token(client) -> str:
    register = client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    return register.json()["token"]


def test_cancel_route_404s_for_unknown_job(client):
    headers = {"Authorization": f"Bearer {_token(client)}"}
    resp = client.post("/api/v1/scan/jobs/no-such-job/cancel", headers=headers)
    assert resp.status_code == 404


def test_cancel_route_on_already_finished_scan_is_a_harmless_no_op(client, tmp_path):
    headers = {"Authorization": f"Bearer {_token(client)}"}
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "jordan.txt").write_bytes(b"Jordan Rivera\njordan.rivera@example.com\nBackend engineer.")

    scan_resp = client.post("/api/v1/scan/folders", json={"folder_paths": [str(resumes_dir)]}, headers=headers)
    job_id = scan_resp.json()["id"]

    import time

    deadline = time.time() + 10
    while time.time() < deadline:
        job = client.get(f"/api/v1/scan/jobs/{job_id}", headers=headers).json()
        if job["status"] != "running":
            break
        time.sleep(0.1)
    assert job["status"] == "completed"
    assert job["cancelled"] is False

    cancel_resp = client.post(f"/api/v1/scan/jobs/{job_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 202
    assert cancel_resp.json()["cancelled"] is False
