"""GET/DELETE /api/v1/dev-tools/sample-sessions — session-tagging for
generated sample data (see app/dev_tools/session_tagging.py). Covers the
real end-to-end path (generate -> scan -> list -> delete) plus the
mixed-ownership case where a candidate has sources from two different
sessions, which must be trimmed rather than fully deleted."""

import time
import uuid
from datetime import datetime
from pathlib import Path

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


def test_generated_session_is_listed_and_deletable_after_scanning(client, tmp_path, monkeypatch):
    # list/delete-session both resolve the generated-data directory via
    # _default_out_dir (settings.mock_email_fixtures_path's parent, same as
    # the real generate-click flow always uses) rather than trusting a
    # custom out_dir passed only to this one generate call.
    out_dir = tmp_path / "sample_data"
    monkeypatch.setenv("MOCK_EMAIL_FIXTURES_PATH", str(out_dir / "emails_manifest.json"))
    from app.dependencies import get_settings

    get_settings.cache_clear()

    gen = client.post(
        "/api/v1/dev-tools/generate-sample-data",
        json={"initial": 5, "followups": 2, "upskill": 0, "seed": 7, "out_dir": str(out_dir), "label": "test batch"},
    )
    assert gen.status_code == 200
    body = gen.json()
    session_id = body["session_id"]
    assert body["label"] == "test batch"

    scan_resp = client.post("/api/v1/scan/folders", json={"folder_paths": [body["resumes_dir"]]})
    job = _wait_for_job(client, scan_resp.json()["id"])
    assert job["status"] == "completed"
    assert job["result"]["candidates_created"] > 0

    sessions = client.get("/api/v1/dev-tools/sample-sessions").json()
    match = next(s for s in sessions if s["id"] == session_id)
    assert match["label"] == "test batch"
    assert match["scanned"] is True
    assert match["candidates_scanned"] == job["result"]["candidates_created"]

    candidates_before = client.get("/api/v1/candidates").json()["total"]
    assert candidates_before > 0

    delete_resp = client.delete(f"/api/v1/dev-tools/sample-sessions/{session_id}")
    assert delete_resp.status_code == 200
    result = delete_resp.json()
    assert result["candidates_deleted"] == job["result"]["candidates_created"]
    assert result["files_deleted"] is True

    candidates_after = client.get("/api/v1/candidates").json()["total"]
    assert candidates_after == 0

    # Un-scanned raw files for this session are gone too, so it can't be
    # re-scanned into life after being deleted.
    remaining = list((out_dir / "resumes").rglob(f"{session_id}__*"))
    assert remaining == []

    sessions_after = client.get("/api/v1/dev-tools/sample-sessions").json()
    assert all(s["id"] != session_id for s in sessions_after)


def test_deleting_unknown_session_404s(client):
    resp = client.delete("/api/v1/dev-tools/sample-sessions/sess-does-not-exist")
    assert resp.status_code == 404


def test_deleting_a_generated_but_never_scanned_session_succeeds(client, tmp_path, monkeypatch):
    """QA regression: a session that was generated but never scanned has no
    ResumeSource rows yet — list_sample_sessions' own docstring says it
    should still be deletable, but the delete route used to 404 before ever
    reaching the file-cleanup path when the DB query came back empty."""
    out_dir = tmp_path / "sample_data"
    monkeypatch.setenv("MOCK_EMAIL_FIXTURES_PATH", str(out_dir / "emails_manifest.json"))
    from app.dependencies import get_settings

    get_settings.cache_clear()

    gen = client.post(
        "/api/v1/dev-tools/generate-sample-data",
        json={"initial": 3, "followups": 0, "upskill": 0, "seed": 3, "out_dir": str(out_dir)},
    )
    session_id = gen.json()["session_id"]

    sessions = client.get("/api/v1/dev-tools/sample-sessions").json()
    assert next(s for s in sessions if s["id"] == session_id)["scanned"] is False

    resp = client.delete(f"/api/v1/dev-tools/sample-sessions/{session_id}")
    assert resp.status_code == 200
    result = resp.json()
    assert result["candidates_deleted"] == 0
    assert result["files_deleted"] is True

    remaining = list((out_dir / "resumes").rglob(f"{session_id}__*"))
    assert remaining == []


def _seed_source(storage, candidate_id: str, session_id: str | None, file_path: Path, tag: str):
    from app.models.db import ResumeSource

    with storage.session() as session:
        session.add(
            ResumeSource(
                id=str(uuid.uuid4()),
                candidate_id=candidate_id,
                origin="folder",
                source_ref=f"/tmp/{tag}",
                content_hash=f"hash-{tag}",
                file_path=str(file_path),
                date_submitted=datetime.utcnow(),
                generation_session_id=session_id,
            )
        )
        session.commit()


def test_candidate_with_sources_from_two_sessions_is_trimmed_not_deleted(client, tmp_path):
    """A candidate regenerated across two sample-data sessions (same
    deterministic person, different runs) has one source per session.
    Deleting one session should remove only that source/file, leaving the
    candidate and the other session's source intact."""
    from app.dependencies import get_storage
    from app.models.db import Candidate

    storage = get_storage()
    candidate_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            Candidate(
                id=candidate_id,
                identity_fingerprint="email:mixed@example.com",
                legal_first_name="Mixed",
                legal_last_name="Owner",
                email="mixed@example.com",
                date_submitted=datetime.utcnow(),
            )
        )
        session.commit()

    dir_a = tmp_path / "session-a"
    dir_b = tmp_path / "session-b"
    dir_a.mkdir()
    dir_b.mkdir()
    file_a = dir_a / "resume.txt"
    file_b = dir_b / "resume.txt"
    file_a.write_text("a")
    file_b.write_text("b")
    (dir_a / "meta.json").write_text(f'{{"candidate_id": "{candidate_id}"}}')
    (dir_b / "meta.json").write_text(f'{{"candidate_id": "{candidate_id}"}}')

    _seed_source(storage, candidate_id, "sess-aaaaaaaa-000000-aaaaaa", file_a, "a")
    _seed_source(storage, candidate_id, "sess-bbbbbbbb-000000-bbbbbb", file_b, "b")

    resp = client.delete("/api/v1/dev-tools/sample-sessions/sess-aaaaaaaa-000000-aaaaaa")
    assert resp.status_code == 200
    result = resp.json()
    assert result["candidates_deleted"] == 0
    assert result["candidates_trimmed"] == 1
    assert result["sources_deleted"] == 1

    with storage.session() as session:
        assert session.get(Candidate, candidate_id) is not None

    assert not file_a.exists()
    assert file_b.exists()


def test_trimming_a_session_does_not_orphan_a_surviving_sessions_file_sharing_the_same_directory(client, tmp_path):
    """QA regression: write_mirror keys the mirror directory on
    candidate + date, not per-submission — a same-day regenerate of the
    same deterministic person (same seed) overwrites the earlier session's
    resume.<ext>/meta.json/profile_summary.md in place with the new run's
    content, so both ResumeSource rows can end up pointing at the exact
    same physical file. Trimming session A must not delete that file (or
    the meta.json/summary the surviving session B source still needs) just
    because session A's DB row happens to reference the same path."""
    from app.dependencies import get_storage
    from app.models.db import Candidate

    storage = get_storage()
    candidate_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            Candidate(
                id=candidate_id,
                identity_fingerprint="email:sameday@example.com",
                legal_first_name="Same",
                legal_last_name="Day",
                email="sameday@example.com",
                date_submitted=datetime.utcnow(),
            )
        )
        session.commit()

    shared_dir = tmp_path / "same-day"
    shared_dir.mkdir()
    shared_file = shared_dir / "resume.txt"
    # Session B's scan physically overwrote session A's file in place —
    # this is the *current* (session B) content by the time either session
    # is deleted.
    shared_file.write_text("session b content")
    (shared_dir / "profile_summary.md").write_text("Summary")
    (shared_dir / "meta.json").write_text(f'{{"candidate_id": "{candidate_id}"}}')

    # Both ResumeSource rows reference the identical on-disk path — exactly
    # what a same-day, same-extension regenerate produces.
    _seed_source(storage, candidate_id, "sess-aaaaaaaa-000000-aaaaaa", shared_file, "a")
    _seed_source(storage, candidate_id, "sess-bbbbbbbb-000000-bbbbbb", shared_file, "b")

    resp = client.delete("/api/v1/dev-tools/sample-sessions/sess-aaaaaaaa-000000-aaaaaa")
    assert resp.status_code == 200
    result = resp.json()
    assert result["candidates_trimmed"] == 1

    with storage.session() as session:
        assert session.get(Candidate, candidate_id) is not None

    # Session B's file must survive — it's the same physical file session A
    # pointed at, but session B still needs it.
    assert shared_file.exists()
    assert shared_file.read_text() == "session b content"
    assert (shared_dir / "meta.json").exists()
    assert (shared_dir / "profile_summary.md").exists()
