"""POST /matches/{job_id}/rescan-matched — bounded rescan of just a job's
already-matched candidates (see routes/match_rescan.py)."""

import time
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

RESUME_TEXT = b"Jordan Rivera\njordan.rivera@example.com\nBackend engineer with Python experience."


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


def test_rescan_matched_unknown_job_404s(client):
    token = _token(client)
    resp = client.post("/api/v1/matches/does-not-exist/rescan-matched", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_rescan_matched_with_no_matches_400s(client):
    from app.dependencies import get_storage
    from app.models.db import Job

    storage = get_storage()
    with storage.session() as session:
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", company="Acme", raw_text="...", active=True)
        session.add(job)
        session.commit()
        job_id = job.id

    token = _token(client)
    resp = client.post(f"/api/v1/matches/{job_id}/rescan-matched", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400


def test_rescan_matched_checks_every_matched_candidate_and_finds_no_updates(client, tmp_path):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "jordan.txt").write_bytes(RESUME_TEXT)
    scan_resp = client.post("/api/v1/scan/folders", json={"folder_paths": [str(resumes_dir)]}, headers=headers)
    _wait_for_job(client, headers, scan_resp.json()["id"])
    candidate_id = client.get("/api/v1/candidates", headers=headers).json()["candidates"][0]["id"]

    from app.dependencies import get_storage
    from app.models.db import Job, Match

    storage = get_storage()
    with storage.session() as session:
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", company="Acme", raw_text="...", active=True)
        session.add(job)
        session.add(
            Match(
                id=str(uuid.uuid4()),
                job_id=job.id,
                candidate_id=candidate_id,
                score=80.0,
                tier="good_match",
                reasons={"matched": [], "gaps": []},
                matched_at=datetime.utcnow(),
            )
        )
        session.commit()
        job_id = job.id

    resp = client.post(f"/api/v1/matches/{job_id}/rescan-matched", headers=headers)
    assert resp.status_code == 202
    result = _wait_for_job(client, headers, resp.json()["id"])

    assert result["status"] == "completed"
    assert result["result"]["resumes_found"] == 1  # 1 candidate checked
    assert result["result"]["candidates_updated"] == 0  # nothing new since the folder is unchanged
