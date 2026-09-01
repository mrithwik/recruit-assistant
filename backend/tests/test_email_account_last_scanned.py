"""EmailAccount.last_scanned_at existed in the model/API response but was
never written anywhere — the Email Access page always showed "never" for a
mailbox that had actually just been scanned successfully. Covers both scan
routes that touch email accounts (scan_email_accounts, scan_all), and the
mock-mode case specifically: the account lookup used to be skipped entirely
under USE_MOCK_EMAIL=true, so even a real connected account row (e.g. the
dev-seeded "demo@mock.local") never got updated by a mock scan."""

import time
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
    # Without this, resolve_mock_manifest_path() falls back to the repo's
    # real sample_data/emails_manifest.json (see scan.py) — this test would
    # silently scan real generated fixture data (thousands of emails,
    # slow) instead of the empty set it actually wants. Point at a path
    # that doesn't exist: load_fixtures_from_manifest() treats that as "no
    # fixtures yet", not an error.
    monkeypatch.setenv("MOCK_EMAIL_FIXTURES_PATH", str(tmp_path / "no_manifest_here.json"))

    from app.dependencies import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def _headers(client) -> dict:
    register = client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
    return {"Authorization": f"Bearer {register.json()['token']}"}


def _seed_account() -> str:
    from app.dependencies import get_storage
    from app.models.db import EmailAccount

    storage = get_storage()
    account_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            EmailAccount(
                id=account_id,
                provider="gmail",
                email_address="mock-account@example.com",
                keychain_ref="",
                status="connected",
            )
        )
        session.commit()
    return account_id


def _wait_for_job(client, headers, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/scan/jobs/{job_id}", headers=headers).json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise TimeoutError("scan job did not finish in time")


def test_mock_scan_of_email_accounts_sets_last_scanned_at(client):
    headers = _headers(client)
    account_id = _seed_account()

    resp = client.post("/api/v1/scan/email-accounts", json={"account_ids": [account_id]}, headers=headers)
    assert resp.status_code == 202
    _wait_for_job(client, headers, resp.json()["id"])

    accounts = client.get("/api/v1/email-accounts", headers=headers).json()
    account = next(a for a in accounts if a["id"] == account_id)
    assert account["last_scanned_at"] is not None
    assert datetime.fromisoformat(account["last_scanned_at"]) > datetime.utcnow().replace(year=2000)


def test_scan_all_sets_last_scanned_at_for_every_connected_account(client):
    headers = _headers(client)
    account_id = _seed_account()

    resp = client.post("/api/v1/scan/all", headers=headers)
    assert resp.status_code == 202
    _wait_for_job(client, headers, resp.json()["id"])

    accounts = client.get("/api/v1/email-accounts", headers=headers).json()
    account = next(a for a in accounts if a["id"] == account_id)
    assert account["last_scanned_at"] is not None
