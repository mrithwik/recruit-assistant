"""POST /candidates/{id}/rescan — targeted rescan of just one candidate's
known sources (see routes/candidate_rescan.py). Exercised end-to-end via
TestClient against the folder path since that needs no OAuth/mock-fixture
setup: a real scan first (to seed a real candidate + ResumeSource), then a
rescan of the same untouched folder should find nothing new."""

import time

import pytest
from fastapi.testclient import TestClient

RESUME_TEXT = (
    b"Jordan Rivera\njordan.rivera@example.com\n"
    b"7 years backend engineering experience with Python, FastAPI, and PostgreSQL."
)


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


def _wait_for_job(client, headers, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/scan/jobs/{job_id}", headers=headers).json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise TimeoutError("job did not finish in time")


def test_rescan_candidate_finds_no_new_resumes_in_unchanged_folder(client, tmp_path):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "jordan.txt").write_bytes(RESUME_TEXT)

    scan_resp = client.post("/api/v1/scan/folders", json={"folder_paths": [str(resumes_dir)]}, headers=headers)
    assert scan_resp.status_code == 202
    scan_job = _wait_for_job(client, headers, scan_resp.json()["id"])
    assert scan_job["status"] == "completed"
    assert scan_job["result"]["candidates_created"] == 1

    candidates = client.get("/api/v1/candidates", headers=headers).json()["candidates"]
    assert len(candidates) == 1
    candidate_id = candidates[0]["id"]

    rescan_resp = client.post(f"/api/v1/candidates/{candidate_id}/rescan", headers=headers)
    assert rescan_resp.status_code == 202
    rescan_job = _wait_for_job(client, headers, rescan_resp.json()["id"])

    assert rescan_job["status"] == "completed"
    assert rescan_job["result"]["resumes_found"] == 1
    assert rescan_job["result"]["candidates_created"] == 0
    assert rescan_job["result"]["duplicates_skipped"] == 1


def test_rescan_unknown_candidate_404s(client):
    token = _token(client)
    resp = client.post("/api/v1/candidates/does-not-exist/rescan", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_rescan_candidate_with_no_email_400s(client, tmp_path):
    # candidate.email is required to scope an email rescan, and the route
    # guards on it before even looking at sources.
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "no_email.txt").write_bytes(b"Just A Name\nNo email address anywhere in this text at all.")

    scan_resp = client.post("/api/v1/scan/folders", json={"folder_paths": [str(resumes_dir)]}, headers=headers)
    _wait_for_job(client, headers, scan_resp.json()["id"])
    candidate_id = client.get("/api/v1/candidates", headers=headers).json()["candidates"][0]["id"]

    resp = client.post(f"/api/v1/candidates/{candidate_id}/rescan", headers=headers)
    assert resp.status_code == 400
