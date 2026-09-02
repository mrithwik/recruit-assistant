"""QA regression, at the route level: one connected mailbox failing mid-scan
must not take the whole /scan/email-accounts job down, and must not
truncate a healthy sibling account's results — see
test_fan_in_ingestor.py for the same guarantee proven directly against
FanInIngestor. This file proves the actual route wires it through
correctly end to end (job completes, healthy account's candidates land,
only the failing account's error and last_scanned_at are affected)."""

import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.ingestor_base import ResumeIngestor

LONG_RESUME_TEMPLATE = (
    "Candidate Number {i}\ncandidate{i}@example.com\n"
    "{years} years of backend engineering experience with Python, FastAPI, "
    "PostgreSQL, and Kubernetes. Led cross-functional teams through several "
    "major platform migrations, owned schema design end to end, and mentored "
    "junior engineers on system design fundamentals and code review practice."
)


class _HealthyIngestor(ResumeIngestor):
    def __init__(self, count: int):
        self.count = count

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        for i in range(self.count):
            yield IngestedResume(
                origin=ResumeOrigin.EMAIL,
                source_ref=f"healthy:{i}",
                file_bytes=LONG_RESUME_TEMPLATE.format(i=i, years=i + 1).encode(),
                filename=f"healthy-{i}.txt",
                date_submitted=datetime(2026, 1, 1),
            )


class _FailingIngestor(ResumeIngestor):
    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        raise RuntimeError("simulated OAuth token expired mid-scan")
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


def _seed_account(email: str) -> str:
    from app.dependencies import get_storage
    from app.models.db import EmailAccount

    storage = get_storage()
    account_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            EmailAccount(id=account_id, provider="gmail", email_address=email, keychain_ref="", status="connected")
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


def test_one_account_failing_does_not_fail_the_job_or_touch_a_healthy_siblings_results(client, monkeypatch):
    healthy_id = _seed_account("healthy@example.com")
    failing_id = _seed_account("failing@example.com")

    import app.routes.scan as scan_module

    def fake_build_email_ingestor(account_id, account, settings, mock_fixtures, sender_email=""):
        if account_id == failing_id:
            return _FailingIngestor(), None
        return _HealthyIngestor(count=5), None

    monkeypatch.setattr(scan_module, "build_email_ingestor", fake_build_email_ingestor)

    resp = client.post("/api/v1/scan/email-accounts", json={"account_ids": [healthy_id, failing_id]})
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["id"])

    # The job as a whole must report success — one account failing is a
    # per-account error, not a job-level failure.
    assert job["status"] == "completed"
    assert job["result"]["candidates_created"] == 5
    assert any("failing@example.com" in e or failing_id in e for e in job["result"]["errors"])

    accounts = {a["id"]: a for a in client.get("/api/v1/email-accounts").json()}
    assert accounts[healthy_id]["last_scanned_at"] is not None
    assert accounts[failing_id]["last_scanned_at"] is None
