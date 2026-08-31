"""GET /maintenance/tasks reports pending_count per task — backs the
Dashboard's "Updates available" banner, which only shows a task once it
actually has pending work (see components/dashboard/pending-updates-banner.tsx)."""

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


def _token(client) -> str:
    register = client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    return register.json()["token"]


def test_pending_count_is_zero_with_no_data(client):
    token = _token(client)
    resp = client.get("/api/v1/maintenance/tasks", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    tasks = {t["id"]: t for t in resp.json()}
    assert tasks["email_link_backfill"]["pending_count"] == 0


def test_pending_count_reflects_sources_missing_email_link(client):
    from app.dependencies import get_storage
    from app.models.db import Candidate, ResumeSource

    storage = get_storage()
    with storage.session() as session:
        candidate = Candidate(
            id=str(uuid.uuid4()),
            identity_fingerprint="email:a@example.com",
            email="a@example.com",
            date_submitted=datetime.utcnow(),
        )
        session.add(candidate)
        session.add(
            ResumeSource(
                id=str(uuid.uuid4()),
                candidate_id=candidate.id,
                origin="email",
                source_ref="me@example.com:msg-1",
                content_hash="h1",
                file_path="/tmp/f1",
                date_submitted=datetime.utcnow(),
                email_link="",
            )
        )
        session.add(
            ResumeSource(
                id=str(uuid.uuid4()),
                candidate_id=candidate.id,
                origin="email",
                source_ref="me@example.com:msg-2",
                content_hash="h2",
                file_path="/tmp/f2",
                date_submitted=datetime.utcnow(),
                email_link="https://mail.google.com/mail/u/0/#all/thread-2",
            )
        )
        session.commit()

    token = _token(client)
    resp = client.get("/api/v1/maintenance/tasks", headers={"Authorization": f"Bearer {token}"})
    tasks = {t["id"]: t for t in resp.json()}
    assert tasks["email_link_backfill"]["pending_count"] == 1
