"""A recruiter's own free-text notes on a candidate — independent of any
one job match (judge_notes and per-flag notes both live on Match, scoped
to one job). See routes/candidates.py's POST/DELETE /notes."""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient


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


def _headers(client) -> dict:
    register = client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    return {"Authorization": f"Bearer {register.json()['token']}"}


def _seed_candidate() -> str:
    from app.dependencies import get_storage
    from app.models.db import Candidate

    storage = get_storage()
    candidate_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            Candidate(
                id=candidate_id,
                identity_fingerprint="email:notes-test@example.com",
                legal_first_name="Notes",
                legal_last_name="Test",
                email="notes-test@example.com",
                date_submitted=datetime.utcnow(),
            )
        )
        session.commit()
    return candidate_id


def test_add_note_appears_newest_first_and_on_candidate_detail(client):
    headers = _headers(client)
    candidate_id = _seed_candidate()

    first = client.post(f"/api/v1/candidates/{candidate_id}/notes", json={"text": "Called, left voicemail"}, headers=headers)
    assert first.status_code == 200
    second = client.post(f"/api/v1/candidates/{candidate_id}/notes", json={"text": "Call back in Q2"}, headers=headers)
    assert second.status_code == 200
    notes = second.json()
    assert [n["text"] for n in notes] == ["Call back in Q2", "Called, left voicemail"]

    detail = client.get(f"/api/v1/candidates/{candidate_id}", headers=headers).json()
    assert [n["text"] for n in detail["recruiter_notes"]] == ["Call back in Q2", "Called, left voicemail"]


def test_delete_note_removes_only_that_one(client):
    headers = _headers(client)
    candidate_id = _seed_candidate()
    client.post(f"/api/v1/candidates/{candidate_id}/notes", json={"text": "Keep me"}, headers=headers)
    to_delete = client.post(f"/api/v1/candidates/{candidate_id}/notes", json={"text": "Delete me"}, headers=headers).json()[0]

    resp = client.delete(f"/api/v1/candidates/{candidate_id}/notes/{to_delete['id']}", headers=headers)
    assert resp.status_code == 200
    assert [n["text"] for n in resp.json()] == ["Keep me"]


def test_empty_note_text_400s(client):
    headers = _headers(client)
    candidate_id = _seed_candidate()
    resp = client.post(f"/api/v1/candidates/{candidate_id}/notes", json={"text": "   "}, headers=headers)
    assert resp.status_code == 400


def test_note_on_unknown_candidate_404s(client):
    headers = _headers(client)
    resp = client.post("/api/v1/candidates/does-not-exist/notes", json={"text": "hi"}, headers=headers)
    assert resp.status_code == 404
