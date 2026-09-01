"""End-to-end auth tests against the real FastAPI app: first-run registration,
login, protected-route gating, and the "registration locks after first
account" behavior."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_EMAIL", "true")

    from app.auth.rate_limit import reset_all
    from app.dependencies import get_settings

    get_settings.cache_clear()
    # rate_limit's _attempts dict is module-level state that outlives any
    # one test's fresh DB — without this, a failed-login test earlier in
    # the same pytest run could leave an email locked out for a later,
    # unrelated test reusing that address.
    reset_all()

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


def test_login_locks_out_after_max_failed_attempts(client):
    from app.auth.rate_limit import MAX_FAILED_ATTEMPTS

    client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})

    for _ in range(MAX_FAILED_ATTEMPTS):
        resp = client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "wrong-password"})
        assert resp.status_code == 401

    # The Nth+1 attempt is locked out even with the CORRECT password now —
    # that's the point: it's the account that's rate-limited, not just
    # continued wrong guesses.
    locked = client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    assert locked.status_code == 429


def test_login_lockout_is_scoped_to_one_email(client):
    from app.auth.rate_limit import MAX_FAILED_ATTEMPTS

    client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})

    for _ in range(MAX_FAILED_ATTEMPTS):
        client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "wrong-password"})

    # A different (nonexistent) email is unaffected by another email's
    # lockout — still a normal 401, not swept into the same 429.
    other = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert other.status_code == 401


def test_successful_login_clears_prior_failed_attempts(client):
    client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})

    client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "wrong-password"})
    client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "wrong-password"})
    good = client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    assert good.status_code == 200

    # Failure count reset by the success above — one more wrong guess
    # shouldn't be attempt #3-toward-lockout, it should be attempt #1.
    bad_again = client.post("/api/v1/auth/login", json={"email": "recruiter@example.com", "password": "wrong-password"})
    assert bad_again.status_code == 401
