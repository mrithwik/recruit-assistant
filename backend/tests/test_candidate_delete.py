"""DELETE /api/v1/candidates/{id} — real, irreversible per-candidate PII
deletion (the proportionate counterpart to dev_tools.clear_data's
wipe-everything danger zone). Confirms the DB cascade (Match, ResumeSource)
and the on-disk mirror cleanup (resume file, profile_summary.md, meta.json)
both happen, and that a second, unrelated candidate's files are untouched."""

import json
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


def _seed_candidate_with_mirror(tmp_path: Path, name: str) -> tuple[str, Path]:
    """Creates a Candidate + one ResumeSource, plus the on-disk mirror
    directory write_mirror would have created for it, so deletion can be
    verified against both the DB and disk."""
    from app.dependencies import get_storage
    from app.models.db import Candidate, ResumeSource
    from app.scanning.mirror_writer import slugify

    storage = get_storage()
    candidate_id = str(uuid.uuid4())
    candidate_slug = slugify(f"{name}-{candidate_id[:8]}")
    target_dir = tmp_path / "candidates" / "unassigned" / "2026-01-01" / candidate_slug
    target_dir.mkdir(parents=True)
    resume_path = target_dir / "resume.pdf"
    resume_path.write_bytes(b"%PDF-fake")
    (target_dir / "profile_summary.md").write_text("Summary")
    (target_dir / "meta.json").write_text(json.dumps({"candidate_id": candidate_id}))

    with storage.session() as session:
        candidate = Candidate(
            id=candidate_id,
            identity_fingerprint=f"email:{name}@example.com",
            legal_first_name=name,
            legal_last_name="Candidate",
            email=f"{name}@example.com",
            date_submitted=datetime.utcnow(),
        )
        session.add(candidate)
        session.add(
            ResumeSource(
                id=str(uuid.uuid4()),
                candidate_id=candidate_id,
                origin="folder",
                source_ref="/tmp/resumes",
                content_hash=f"hash-{name}",
                file_path=str(resume_path),
                date_submitted=datetime.utcnow(),
            )
        )
        session.commit()
    return candidate_id, target_dir


def test_delete_candidate_removes_db_rows_and_mirror_files(client, tmp_path):
    from app.dependencies import get_storage
    from app.models.db import Candidate, Job, Match, ResumeSource

    candidate_id, target_dir = _seed_candidate_with_mirror(tmp_path, "Erase Me")
    storage = get_storage()
    with storage.session() as session:
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", raw_text="...", active=True)
        session.add(job)
        session.add(
            Match(
                id=str(uuid.uuid4()),
                job_id=job.id,
                candidate_id=candidate_id,
                score=80.0,
                tier="good_match",
                reasons={"matched": [], "gaps": []},
                missing_info=[],
                flags=[],
            )
        )
        session.commit()

    resp = client.delete(f"/api/v1/candidates/{candidate_id}")
    assert resp.status_code == 204

    with storage.session() as session:
        assert session.get(Candidate, candidate_id) is None
        assert session.query(Match).filter(Match.candidate_id == candidate_id).count() == 0
        assert session.query(ResumeSource).filter(ResumeSource.candidate_id == candidate_id).count() == 0

    assert not target_dir.exists()


def test_delete_candidate_404s_on_unknown_id(client):
    resp = client.delete(f"/api/v1/candidates/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_candidate_leaves_other_candidates_mirror_files_untouched(client, tmp_path):
    victim_id, victim_dir = _seed_candidate_with_mirror(tmp_path, "Erase Me")
    bystander_id, bystander_dir = _seed_candidate_with_mirror(tmp_path, "Keep Me")

    resp = client.delete(f"/api/v1/candidates/{victim_id}")
    assert resp.status_code == 204

    assert not victim_dir.exists()
    assert bystander_dir.exists()
    assert (bystander_dir / "resume.pdf").exists()

    from app.dependencies import get_storage
    from app.models.db import Candidate

    storage = get_storage()
    with storage.session() as session:
        assert session.get(Candidate, bystander_id) is not None
