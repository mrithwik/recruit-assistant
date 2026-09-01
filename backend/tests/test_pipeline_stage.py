"""POST /matches/{id}/stage — a candidate's status in the hiring process for
one job (sourced/screened/submitted/interviewing/offer/placed/declined),
independent of tier. Confirms the new stage is persisted and shows up
everywhere a Match is surfaced: the match itself, the candidate detail page's
per-job match list, and the job's match list."""

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


def _seed_match(candidate_name="Interviewing Candidate"):
    from app.dependencies import get_storage
    from app.models.db import Candidate, Job, Match

    storage = get_storage()
    with storage.session() as session:
        candidate = Candidate(
            id=str(uuid.uuid4()),
            identity_fingerprint=f"email:{candidate_name}@example.com",
            legal_first_name=candidate_name,
            legal_last_name="Candidate",
            email=f"{candidate_name}@example.com",
            date_submitted=datetime.utcnow(),
        )
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", company="Acme", raw_text="...", active=True)
        session.add(candidate)
        session.add(job)
        match = Match(
            id=str(uuid.uuid4()),
            job_id=job.id,
            candidate_id=candidate.id,
            score=80.0,
            tier="good_match",
            reasons={"matched": [], "gaps": []},
            missing_info=[],
            flags=[],
        )
        session.add(match)
        session.commit()
        return match.id, job.id, candidate.id


def test_new_match_defaults_to_sourced(client):
    match_id, job_id, _ = _seed_match()
    token = _token(client)
    resp = client.get(f"/api/v1/matches/{job_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["matches"][0]["pipeline_stage"] == "sourced"


def test_updating_stage_persists_and_shows_on_match_and_candidate_detail(client):
    match_id, job_id, candidate_id = _seed_match()
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/api/v1/matches/{match_id}/stage", json={"stage": "interviewing"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["pipeline_stage"] == "interviewing"

    match_list = client.get(f"/api/v1/matches/{job_id}", headers=headers).json()["matches"]
    assert match_list[0]["pipeline_stage"] == "interviewing"

    candidate_detail = client.get(f"/api/v1/candidates/{candidate_id}", headers=headers).json()
    assert candidate_detail["matches"][0]["pipeline_stage"] == "interviewing"


def test_updating_stage_on_missing_match_404s(client):
    token = _token(client)
    resp = client.post(
        f"/api/v1/matches/{uuid.uuid4()}/stage",
        json={"stage": "offer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_updating_stage_with_invalid_value_422s(client):
    match_id, _, _ = _seed_match()
    token = _token(client)
    resp = client.post(
        f"/api/v1/matches/{match_id}/stage",
        json={"stage": "not_a_real_stage"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
