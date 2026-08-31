"""GET/PATCH /api/v1/settings/mock-mode — the live runtime toggle that lets
the UI switch email/LLM mock vs. real without restarting the backend (see
app/runtime_settings.py). Covers the guardrail: real LLM mode must be
refused when no provider key is configured, rather than silently accepted
and failing mid-scan."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_EMAIL", "true")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.dependencies import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
        c.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
        yield c

    get_settings.cache_clear()


def test_get_reports_current_mock_state(client):
    resp = client.get("/api/v1/settings/mock-mode")
    assert resp.status_code == 200
    body = resp.json()
    assert body["use_mock_llm"] is True
    assert body["use_mock_email"] is True
    assert body["real_llm_available"] is False  # no key configured in this fixture
    assert body["expose_toggle"] is True


def test_patch_toggles_email_mock_off(client):
    resp = client.patch("/api/v1/settings/mock-mode", json={"use_mock_email": False})
    assert resp.status_code == 200
    assert resp.json()["use_mock_email"] is False
    assert resp.json()["use_mock_llm"] is True  # untouched

    # And it's live — a second GET reflects it, no restart needed.
    assert client.get("/api/v1/settings/mock-mode").json()["use_mock_email"] is False


def test_patch_refuses_real_llm_mode_without_a_configured_key(client):
    resp = client.patch("/api/v1/settings/mock-mode", json={"use_mock_llm": False})
    assert resp.status_code == 400
    assert "no OPENROUTER_API_KEY or OPENAI_API_KEY" in resp.json()["detail"]

    # Rejected — still mock afterward, nothing silently changed.
    assert client.get("/api/v1/settings/mock-mode").json()["use_mock_llm"] is True


def test_patch_still_refuses_if_key_was_added_after_startup(client, monkeypatch):
    """A key dropped into .env after the backend already started doesn't
    retroactively give the already-built DispatcherLLMClient a real client
    — this must still be refused, not silently pass on a re-read of .env
    while actually falling back to mock underneath (see mock_mode.py)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake-test-key")
    from app.dependencies import get_settings

    get_settings.cache_clear()

    resp = client.patch("/api/v1/settings/mock-mode", json={"use_mock_llm": False})
    assert resp.status_code == 400


def test_patch_allows_real_llm_mode_when_a_key_was_configured_at_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_EMAIL", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake-test-key")

    from app.dependencies import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
        c.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})

        patch_resp = c.patch("/api/v1/settings/mock-mode", json={"use_mock_llm": False})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["use_mock_llm"] is False
    get_settings.cache_clear()


def test_unauthenticated_request_is_rejected():
    from app.dependencies import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        resp = c.get("/api/v1/settings/mock-mode")
    assert resp.status_code == 401
    get_settings.cache_clear()
