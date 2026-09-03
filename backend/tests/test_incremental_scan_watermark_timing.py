"""QA finding on the incremental-scan lever: last_scanned_at/last_run_at
must be captured from *before* the mailbox fetch runs, not after the whole
scan (including real parse/summarize LLM calls, which can take minutes at
real volume) finishes — otherwise a message that arrives mid-scan has a
received-date earlier than the recorded watermark but was never in this
scan's own results, and every future incremental scan's date_start filter
silently and permanently excludes it. Proven here with an ingestor that
sleeps before yielding, so "watermark stamped after completion" and
"watermark stamped before the fetch" are distinguishable by elapsed time."""

import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.ingestor_base import ResumeIngestor

RESUME_TEXT = b"Jordan Rivera\njordan.rivera@example.com\n7 years backend engineering experience."
SLOW_SECONDS = 0.4


class _SlowIngestor(ResumeIngestor):
    """Sleeps before yielding, standing in for a scan that takes real wall-
    clock time to process (real-LLM parse/summarize calls) after its
    mailbox search has already run."""

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        await __import__("asyncio").sleep(SLOW_SECONDS)
        yield IngestedResume(
            origin=ResumeOrigin.EMAIL,
            source_ref="slow:0",
            file_bytes=RESUME_TEXT,
            filename="jordan.txt",
            date_submitted=datetime(2026, 1, 1),
        )


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


def _seed_account() -> str:
    from app.dependencies import get_storage
    from app.models.db import EmailAccount

    storage = get_storage()
    account_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            EmailAccount(id=account_id, provider="gmail", email_address=f"{account_id}@example.com", keychain_ref="", status="connected")
        )
        session.commit()
    return account_id


def _wait_for_job(client, job_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/scan/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise TimeoutError("job did not finish in time")


def test_watermark_is_stamped_before_the_scan_not_after_it_completes(client, monkeypatch):
    account_id = _seed_account()

    import app.routes.scan as scan_module

    monkeypatch.setattr(scan_module, "build_email_ingestor", lambda *a, **k: (_SlowIngestor(), None))

    request_sent_at = datetime.utcnow()
    resp = client.post("/api/v1/scan/email-accounts", json={"account_ids": [account_id]})
    job = _wait_for_job(client, resp.json()["id"])
    request_completed_at = datetime.utcnow()

    assert job["status"] == "completed"
    assert job["result"]["candidates_created"] == 1

    accounts = {a["id"]: a for a in client.get("/api/v1/email-accounts").json()}
    last_scanned_at = datetime.fromisoformat(accounts[account_id]["last_scanned_at"])

    # A watermark stamped after completion would land within a few ms of
    # request_completed_at; one stamped before the (slow) fetch lands close
    # to request_sent_at instead — well before completion, by roughly
    # SLOW_SECONDS.
    assert request_sent_at <= last_scanned_at <= request_completed_at
    assert (request_completed_at - last_scanned_at).total_seconds() >= SLOW_SECONDS * 0.5
