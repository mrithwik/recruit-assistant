"""End-to-end auth tests against the real FastAPI app: first-run registration,
login, protected-route gating, and the "registration locks after first
account" behavior."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("USE_MOCK", "true")

    from app.dependencies import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def test_status_false_before_any_account_exists(client):
    resp = client.get("/api/v1/auth/status")
    assert resp.json() == {"setup_complete": False}


def test_protected_route_rejects_missing_token(client):
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 401


def test_protected_route_rejects_garbage_token(client):
    resp = client.get("/api/v1/jobs", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_register_then_access_protected_route(client):
    resp = client.post(
        "/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"}
    )
    assert resp.status_code == 200
    token = resp.json()["token"]

    jobs_resp = client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"})
    assert jobs_resp.status_code == 200
    assert jobs_resp.json() == []


def test_registration_locks_after_first_account(client):
    first = client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "correct-horse-battery"})
    assert first.status_code == 200

    second = client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "correct-horse-battery"})
    assert second.status_code == 403


def test_login_success_and_wrong_password(client):
    client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})

    good = client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    assert good.status_code == 200
    assert "token" in good.json()

    bad = client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "wrong-password"})
    assert bad.status_code == 401


def test_register_rejects_weak_password(client):
    resp = client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "short"})
    assert resp.status_code == 400
