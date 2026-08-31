"""Soft-delete/undo path for jobs (routes/jobs.py) — a job that's deleted
(deactivated) drops out of GET /jobs, shows up under GET /jobs/inactive,
and POST /{id}/reactivate brings it back. Backs the Jobs page's "Inactive
jobs" section, the permanent undo path once a delete toast's own Undo
button has timed out."""

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


def test_deactivated_job_moves_from_active_to_inactive_list(client):
    headers = _headers(client)
    created = client.post(
        "/api/v1/jobs", json={"title": "Backend Engineer", "raw_text": "Python, FastAPI", "company": "Acme"}, headers=headers
    ).json()
    job_id = created["id"]

    assert any(j["id"] == job_id for j in client.get("/api/v1/jobs", headers=headers).json())

    client.delete(f"/api/v1/jobs/{job_id}", headers=headers)

    assert not any(j["id"] == job_id for j in client.get("/api/v1/jobs", headers=headers).json())
    assert any(j["id"] == job_id for j in client.get("/api/v1/jobs/inactive", headers=headers).json())


def test_reactivate_moves_job_back_to_active_list(client):
    headers = _headers(client)
    created = client.post(
        "/api/v1/jobs", json={"title": "Platform Engineer", "raw_text": "Go, Kubernetes", "company": "Acme"}, headers=headers
    ).json()
    job_id = created["id"]
    client.delete(f"/api/v1/jobs/{job_id}", headers=headers)

    reactivate = client.post(f"/api/v1/jobs/{job_id}/reactivate", headers=headers)
    assert reactivate.status_code == 200

    assert any(j["id"] == job_id for j in client.get("/api/v1/jobs", headers=headers).json())
    assert not any(j["id"] == job_id for j in client.get("/api/v1/jobs/inactive", headers=headers).json())


def test_reactivate_unknown_job_404s(client):
    headers = _headers(client)
    resp = client.post("/api/v1/jobs/does-not-exist/reactivate", headers=headers)
    assert resp.status_code == 404
