"""POST /scan/all — the All Candidates page's "Rescan all for updates"
button: one combined pass over every known folder path + connected account,
rather than one scan per candidate (see routes/scan.py's scan_all docstring
for why that distinction matters at real volume)."""

import time

import pytest
from fastapi.testclient import TestClient

RESUME_TEXT = b"Jordan Rivera\njordan.rivera@example.com\nBackend engineer."


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


def test_scan_all_with_no_sources_400s(client):
    token = _token(client)
    resp = client.post("/api/v1/scan/all", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400


def test_scan_all_rescans_known_folder(client, tmp_path):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "jordan.txt").write_bytes(RESUME_TEXT)

    scan_resp = client.post("/api/v1/scan/folders", json={"folder_paths": [str(resumes_dir)]}, headers=headers)
    _wait_for_job(client, headers, scan_resp.json()["id"])

    all_resp = client.post("/api/v1/scan/all", headers=headers)
    assert all_resp.status_code == 202
    job = _wait_for_job(client, headers, all_resp.json()["id"])
    assert job["status"] == "completed"
    assert job["result"]["resumes_found"] == 1
    assert job["result"]["duplicates_skipped"] == 1


