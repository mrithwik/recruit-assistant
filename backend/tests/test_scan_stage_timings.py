"""QA regression: ScanResult.stage_timings was correctly computed by each
individual run_scan() call, but the multi-source routes (scan_email_accounts,
scan_all) only accumulated the older fields (resumes_found,
candidates_created, ...) into their combined result — stage_timings stayed
at its {} default even though real work happened. Confirms both routes'
*completed* job result carries non-trivial, merged stage_timings across more
than one source."""

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

    from app.dependencies import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"})
        c.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
        yield c

    get_settings.cache_clear()


def _wait_for_job(client, job_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/scan/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise TimeoutError("job did not finish in time")


def _seed_account(email: str) -> str:
    from app.dependencies import get_storage
    from app.models.db import EmailAccount

    storage = get_storage()
    account_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            EmailAccount(
                id=account_id,
                provider="gmail",
                email_address=email,
                keychain_ref="",
                status="connected",
            )
        )
        session.commit()
    return account_id


def test_scan_email_accounts_does_not_drop_stage_timings_across_multiple_accounts(client, tmp_path, monkeypatch):
    out_dir = tmp_path / "sample_data"
    monkeypatch.setenv("MOCK_EMAIL_FIXTURES_PATH", str(out_dir / "emails_manifest.json"))
    from app.dependencies import get_settings

    get_settings.cache_clear()

    # A larger batch than the bug strictly needs — see
    # test_stage_timings_rounding.py for a deterministic (non-timing-based)
    # proof of the actual bug. This is a live smoke test on top of that, so
    # its real parse time needs enough margin above the 0.005s rounding
    # threshold to not be flaky on a fast machine (5 resumes measured as
    # low as ~0.00s in practice, since only one of the two accounts below
    # ends up contributing real work — the other dedupes to zero).
    client.post(
        "/api/v1/dev-tools/generate-sample-data",
        json={"initial": 60, "followups": 0, "upskill": 0, "seed": 4, "out_dir": str(out_dir)},
    )

    account_a = _seed_account("a@example.com")
    account_b = _seed_account("b@example.com")

    resp = client.post("/api/v1/scan/email-accounts", json={"account_ids": [account_a, account_b]})
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed"

    timings = job["result"]["stage_timings"]
    assert set(timings) == {"parse", "summarize", "mirror_write", "embed"}
    # Real work happened (60 resumes parsed for the first account; the
    # second account sees identical fixtures and dedupes as already-seen),
    # so the combined result must show it, not the {} it silently dropped
    # to before this fix.
    assert timings["parse"] > 0
    assert sum(timings.values()) > 0


def test_scan_all_does_not_drop_stage_timings_across_folder_and_email_branches(client, tmp_path, monkeypatch):
    out_dir = tmp_path / "sample_data"
    monkeypatch.setenv("MOCK_EMAIL_FIXTURES_PATH", str(out_dir / "emails_manifest.json"))
    from app.dependencies import get_settings

    get_settings.cache_clear()

    # See the note in the test above on why this uses a larger batch than
    # the bug strictly needs.
    gen = client.post(
        "/api/v1/dev-tools/generate-sample-data",
        json={"initial": 60, "followups": 0, "upskill": 0, "seed": 6, "out_dir": str(out_dir)},
    ).json()

    # Seeds a folder-origin ResumeSource so scan_all's folder_paths query
    # (known folders from prior scans) picks this directory up, exercising
    # scan_all's folder branch.
    folder_scan = client.post("/api/v1/scan/folders", json={"folder_paths": [gen["resumes_dir"]]})
    _wait_for_job(client, folder_scan.json()["id"])

    _seed_account("c@example.com")

    resp = client.post("/api/v1/scan/all")
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed"

    timings = job["result"]["stage_timings"]
    assert set(timings) == {"parse", "summarize", "mirror_write", "embed"}
    # The folder branch re-scans already-seen files (dedup skips them
    # before parsing), but the email branch sees the same people through a
    # different source_ref, so it isn't deduped — real parse/mirror-write
    # time from that branch must survive being merged into `combined`.
    assert timings["parse"] > 0
    assert sum(timings.values()) > 0
