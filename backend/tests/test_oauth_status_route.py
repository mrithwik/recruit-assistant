"""GET /email-accounts/oauth-status — backs the setup-instructions banner
on the Email Access page for a fresh deploy with no OAuth client configured
yet (see components/scan/oauth-setup-guide.tsx)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_EMAIL", "true")
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("MS_OAUTH_CLIENT_ID", raising=False)

    from app.dependencies import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def _token(client) -> str:
    register = client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    return register.json()["token"]


def test_oauth_status_reports_unconfigured_when_no_env_vars_set(client):
    token = _token(client)
    resp = client.get("/api/v1/email-accounts/oauth-status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"google_configured": False, "microsoft_configured": False}


def test_oauth_status_reports_configured_when_client_id_present(client, monkeypatch):
    from app.dependencies import get_settings

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "fake-client-id")
    get_settings.cache_clear()

    token = _token(client)
    resp = client.get("/api/v1/email-accounts/oauth-status", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["google_configured"] is True
    assert resp.json()["microsoft_configured"] is False


def test_oauth_status_requires_auth(client):
    resp = client.get("/api/v1/email-accounts/oauth-status")
    assert resp.status_code == 401
