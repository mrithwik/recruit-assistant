"""End-to-end against the real FastAPI app — the CRUD behind the Scan
Sources page's "auto-scan nightly" checkbox (see routes/scheduled_sources.py)."""

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


@pytest.fixture
def auth_headers(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "v@example.com", "password": "verifypass123", "name": "V", "remember": True},
    )
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_add_list_and_remove_scheduled_source(client, auth_headers):
    resp = client.post(
        "/api/v1/scheduled-sources",
        json={"kind": "folder", "ref": "/Users/me/Resumes", "include_subfolders": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    source_id = resp.json()["id"]

    listed = client.get("/api/v1/scheduled-sources", headers=auth_headers).json()
    assert len(listed) == 1
    assert listed[0]["ref"] == "/Users/me/Resumes"
    assert listed[0]["last_run_at"] is None

    resp = client.delete(f"/api/v1/scheduled-sources/{source_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert client.get("/api/v1/scheduled-sources", headers=auth_headers).json() == []


def test_adding_the_same_source_twice_does_not_duplicate(client, auth_headers):
    payload = {"kind": "folder", "ref": "/Users/me/Resumes", "include_subfolders": True}
    first = client.post("/api/v1/scheduled-sources", json=payload, headers=auth_headers).json()
    second = client.post("/api/v1/scheduled-sources", json=payload, headers=auth_headers).json()

    assert first["id"] == second["id"]
    assert len(client.get("/api/v1/scheduled-sources", headers=auth_headers).json()) == 1


def test_invalid_kind_rejected(client, auth_headers):
    resp = client.post(
        "/api/v1/scheduled-sources", json={"kind": "carrier-pigeon", "ref": "x"}, headers=auth_headers
    )
    assert resp.status_code == 400


def test_removing_unknown_source_404s(client, auth_headers):
    resp = client.delete("/api/v1/scheduled-sources/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404


def test_scheduled_sources_route_requires_auth(client):
    resp = client.get("/api/v1/scheduled-sources")
    assert resp.status_code == 401
