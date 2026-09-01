"""POST /candidates/export-selected — CSV of exactly the hand-picked ids
from the All Candidates bulk-select bar, as opposed to /export's "everything
matching the current filters"."""

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


def test_export_selected_includes_only_chosen_ids(client):
    from app.dependencies import get_storage
    from app.models.db import Candidate

    storage = get_storage()
    ids = []
    with storage.session() as session:
        for name in ["Ada Lovelace", "Grace Hopper", "Alan Turing"]:
            first, last = name.split(" ")
            cid = str(uuid.uuid4())
            ids.append(cid)
            session.add(
                Candidate(
                    id=cid,
                    identity_fingerprint=f"email:{first.lower()}@example.com",
                    legal_first_name=first,
                    legal_last_name=last,
                    email=f"{first.lower()}@example.com",
                    date_submitted=datetime.utcnow(),
                )
            )
        session.commit()

    headers = _headers(client)
    resp = client.post("/api/v1/candidates/export-selected", json={"ids": [ids[0], ids[2]]}, headers=headers)
    assert resp.status_code == 200
    assert "attachment; filename=candidates-selected.csv" in resp.headers["content-disposition"]

    body = resp.text
    assert "Ada Lovelace" in body
    assert "Alan Turing" in body
    assert "Grace Hopper" not in body
