"""GET /candidates/{id} must surface each match's red flags / missing info /
judge notes, not just tier+score — the dashboard's Needs Attention "Review"
link lands here, and without this detail there was nothing on the page
explaining *why* a match needed a look (see CandidateMatchDetail)."""

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


def test_candidate_detail_includes_flags_missing_info_and_judge_notes(client):
    from app.dependencies import get_storage
    from app.models.db import Candidate, Job, Match

    storage = get_storage()

    with storage.session() as session:
        candidate = Candidate(
            id=str(uuid.uuid4()),
            identity_fingerprint="email:flagged@example.com",
            legal_first_name="Flagged",
            legal_last_name="Candidate",
            email="flagged@example.com",
            date_submitted=datetime.utcnow(),
        )
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", company="Acme", raw_text="...", active=True)
        session.add(candidate)
        session.add(job)
        session.add(
            Match(
                id=str(uuid.uuid4()),
                job_id=job.id,
                candidate_id=candidate.id,
                score=22.0,
                tier="red_flagged",
                reasons={"matched": ["Python"], "gaps": ["No leadership experience"]},
                missing_info=["Years of experience unclear"],
                flags=[{"color": "red", "note": "Visa status unclear", "added_by": "system"}],
                judge_notes="Judge: score corrected down due to missing visa info.",
            )
        )
        session.commit()
        candidate_id = candidate.id

    token = _token(client)
    resp = client.get(f"/api/v1/candidates/{candidate_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["tier"] == "red_flagged"
    assert match["missing_info"] == ["Years of experience unclear"]
    assert match["reasons"]["gaps"] == ["No leadership experience"]
    assert match["flags"][0]["color"] == "red"
    assert "visa info" in match["judge_notes"]
