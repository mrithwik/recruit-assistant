"""The "All / Real / Mock" data-mode filter — lets a recruiter who loaded a
large sample dataset for testing view/work with just real candidates, or
just the sample set. Classification lives in app/data_classification.py:
mock email fixtures always use the literal source_ref prefix
"mock-demo-mailbox:" (see scanning/email_ingestor.py's MockEmailIngestor),
which is what this pins."""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models.db import Candidate, ResumeSource


def _make(email, source_ref, origin="email"):
    candidate = Candidate(
        id=str(uuid.uuid4()),
        identity_fingerprint=f"email:{email}",
        email=email,
        date_submitted=datetime.utcnow(),
    )
    source = ResumeSource(
        id=str(uuid.uuid4()),
        candidate_id=candidate.id,
        origin=origin,
        source_ref=source_ref,
        content_hash=f"hash:{email}",
        file_path=f"/tmp/{email}",
        date_submitted=candidate.date_submitted,
    )
    return candidate, source


def _seed(storage):
    with storage.session() as session:
        real_candidate, real_source = _make("real@example.com", "me@gmail.com:msg-1")
        mock_candidate, mock_source = _make("mock@example.com", "mock-demo-mailbox:app-1")
        session.add_all([real_candidate, real_source, mock_candidate, mock_source])
        session.commit()
        return real_candidate.id, mock_candidate.id


def test_candidates_page_filters_by_data_mode(storage):
    real_id, mock_id = _seed(storage)
    with storage.session() as session:
        all_candidates, all_total = storage.candidates_page(session, None, None, None, None, "recent", 50, 0)
        real_candidates, real_total = storage.candidates_page(
            session, None, None, None, None, "recent", 50, 0, data_mode="real"
        )
        mock_candidates, mock_total = storage.candidates_page(
            session, None, None, None, None, "recent", 50, 0, data_mode="mock"
        )

    assert all_total == 2
    assert real_total == 1 and real_candidates[0].id == real_id
    assert mock_total == 1 and mock_candidates[0].id == mock_id


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


def test_data_mode_counts_route(client):
    from app.dependencies import get_storage

    storage = get_storage()
    _seed(storage)

    register = client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    token = register.json()["token"]

    resp = client.get("/api/v1/candidates/data-mode-counts", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"real": 1, "mock": 1, "total": 2}


def test_run_matching_scopes_candidate_pool_by_data_mode(client):
    from app.dependencies import get_storage

    storage = get_storage()
    real_id, mock_id = _seed(storage)

    register = client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    headers = {"Authorization": f"Bearer {register.json()['token']}"}

    job_resp = client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "raw_text": "Looking for a backend engineer with Python experience."},
        headers=headers,
    )
    job_id = job_resp.json()["id"]

    resp = client.post(f"/api/v1/matches/run/{job_id}?data_mode=real", headers=headers)
    assert resp.status_code == 200
    matched_ids = {m["candidate"]["id"] for m in resp.json()["matches"]}
    assert matched_ids == {real_id}
    assert mock_id not in matched_ids
