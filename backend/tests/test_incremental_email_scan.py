"""Speed-plan lever — incremental email scan: an account that's already
been scanned should only have mail since its own last_scanned_at re-fetched
and re-parsed on a routine scan, not its entire history every time. Proves
_effective_date_start's three cases (explicit override, full_rescan,
default-to-last-scanned) end to end through the real /scan/email-accounts
and /scan/all routes, plus the per-account isolation (one account's default
start must not leak into a sibling account's)."""

import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.ingestor_base import ResumeIngestor


class _RecordingIngestor(ResumeIngestor):
    """Yields nothing — just records the date_start it was actually called
    with, so tests can assert on what the route computed and passed down
    without needing a real mailbox fixture."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        self.calls.append((date_start, date_end))
        return
        yield  # pragma: no cover - unreachable, makes this an async generator


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_EMAIL", "true")
    monkeypatch.setenv("MOCK_EMAIL_FIXTURES_PATH", str(tmp_path / "no_manifest_here.json"))

    from app.dependencies import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
        c.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
        yield c

    get_settings.cache_clear()


def _seed_account(last_scanned_at: datetime | None) -> str:
    from app.dependencies import get_storage
    from app.models.db import EmailAccount

    storage = get_storage()
    account_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            EmailAccount(
                id=account_id,
                provider="gmail",
                email_address=f"{account_id}@example.com",
                keychain_ref="",
                status="connected",
                last_scanned_at=last_scanned_at,
            )
        )
        session.commit()
    return account_id


def _wait_for_job(client, job_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/scan/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise TimeoutError("job did not finish in time")


def test_account_with_no_explicit_date_defaults_to_its_own_last_scanned_at(client, monkeypatch):
    watermark = datetime(2026, 8, 1, 12, 0, 0)
    account_id = _seed_account(last_scanned_at=watermark)

    import app.routes.scan as scan_module

    recorder = _RecordingIngestor()
    monkeypatch.setattr(scan_module, "build_email_ingestor", lambda *a, **k: (recorder, None))

    resp = client.post("/api/v1/scan/email-accounts", json={"account_ids": [account_id]})
    job = _wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed"
    assert recorder.calls == [(watermark, None)]


def test_never_scanned_account_defaults_to_full_history(client, monkeypatch):
    account_id = _seed_account(last_scanned_at=None)

    import app.routes.scan as scan_module

    recorder = _RecordingIngestor()
    monkeypatch.setattr(scan_module, "build_email_ingestor", lambda *a, **k: (recorder, None))

    resp = client.post("/api/v1/scan/email-accounts", json={"account_ids": [account_id]})
    job = _wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed"
    assert recorder.calls == [(None, None)]


def test_explicit_date_start_overrides_the_account_watermark(client, monkeypatch):
    watermark = datetime(2026, 8, 1, 12, 0, 0)
    account_id = _seed_account(last_scanned_at=watermark)

    import app.routes.scan as scan_module

    recorder = _RecordingIngestor()
    monkeypatch.setattr(scan_module, "build_email_ingestor", lambda *a, **k: (recorder, None))

    explicit = "2020-01-01T00:00:00"
    resp = client.post(
        "/api/v1/scan/email-accounts", json={"account_ids": [account_id], "date_start": explicit}
    )
    job = _wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed"
    assert recorder.calls == [(datetime(2020, 1, 1), None)]


def test_full_rescan_ignores_the_watermark(client, monkeypatch):
    watermark = datetime(2026, 8, 1, 12, 0, 0)
    account_id = _seed_account(last_scanned_at=watermark)

    import app.routes.scan as scan_module

    recorder = _RecordingIngestor()
    monkeypatch.setattr(scan_module, "build_email_ingestor", lambda *a, **k: (recorder, None))

    resp = client.post(
        "/api/v1/scan/email-accounts", json={"account_ids": [account_id], "full_rescan": True}
    )
    job = _wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed"
    assert recorder.calls == [(None, None)]


def test_two_accounts_with_different_watermarks_are_scanned_independently(client, monkeypatch):
    older = datetime(2026, 1, 1)
    newer = datetime(2026, 8, 1)
    account_a = _seed_account(last_scanned_at=older)
    account_b = _seed_account(last_scanned_at=newer)

    import app.routes.scan as scan_module

    recorders: dict[str, _RecordingIngestor] = {}

    def fake_build_email_ingestor(account_id, account, settings, mock_fixtures, sender_email=""):
        rec = _RecordingIngestor()
        recorders[account_id] = rec
        return rec, None

    monkeypatch.setattr(scan_module, "build_email_ingestor", fake_build_email_ingestor)

    resp = client.post(
        "/api/v1/scan/email-accounts", json={"account_ids": [account_a, account_b]}
    )
    job = _wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed"
    assert recorders[account_a].calls == [(older, None)]
    assert recorders[account_b].calls == [(newer, None)]


def test_scan_all_defaults_every_account_to_its_own_watermark_and_full_rescan_overrides(client, monkeypatch):
    # Mock mode auto-seeds a "demo@mock.local" EmailAccount on startup (see
    # app/dependencies.py) — /scan/all sweeps every connected account, so
    # that demo row is in scope here too. Track calls per account_id
    # instead of asserting on one shared recorder's whole call list.
    watermark = datetime(2026, 8, 1, 12, 0, 0)
    account_id = _seed_account(last_scanned_at=watermark)

    import app.routes.scan as scan_module

    recorders: dict[str, _RecordingIngestor] = {}

    def fake_build_email_ingestor(acct_id, account, settings, mock_fixtures, sender_email=""):
        rec = _RecordingIngestor()
        recorders[acct_id] = rec
        return rec, None

    monkeypatch.setattr(scan_module, "build_email_ingestor", fake_build_email_ingestor)

    resp = client.post("/api/v1/scan/all")
    job = _wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed"
    assert recorders[account_id].calls == [(watermark, None)]

    recorders.clear()
    resp2 = client.post("/api/v1/scan/all", params={"full_rescan": "true"})
    job2 = _wait_for_job(client, resp2.json()["id"])
    assert job2["status"] == "completed"
    assert recorders[account_id].calls == [(None, None)]
