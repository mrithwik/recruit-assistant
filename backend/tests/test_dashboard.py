import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.dashboard.service import build_dashboard_summary
from app.models.db import Candidate, Job, Match, ResumeSource


def _seed(storage) -> str:
    """Seeds one job, two candidates (one via email, one via folder), and
    matches at different tiers so every widget has something to aggregate."""
    with storage.session() as session:
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", raw_text="Python, FastAPI")
        session.add(job)

        c1 = Candidate(
            id=str(uuid.uuid4()),
            identity_fingerprint="email:a@example.com",
            legal_first_name="Ada",
            legal_last_name="Lovelace",
            email="a@example.com",
            work_visa_status="us_citizen",
            skills=["python", "fastapi"],
            date_submitted=datetime.utcnow(),
        )
        c2 = Candidate(
            id=str(uuid.uuid4()),
            identity_fingerprint="email:b@example.com",
            legal_first_name="Grace",
            legal_last_name="Hopper",
            email="b@example.com",
            work_visa_status="h1b",
            skills=["python", "sql"],
            date_submitted=datetime.utcnow(),
        )
        session.add_all([c1, c2])
        session.flush()

        session.add_all(
            [
                ResumeSource(
                    id=str(uuid.uuid4()),
                    candidate_id=c1.id,
                    origin="email",
                    source_ref="acct:msg1",
                    content_hash="h1",
                    file_path="/tmp/a",
                    date_submitted=datetime.utcnow(),
                ),
                ResumeSource(
                    id=str(uuid.uuid4()),
                    candidate_id=c2.id,
                    origin="folder",
                    source_ref="/tmp/resumes",
                    content_hash="h2",
                    file_path="/tmp/b",
                    date_submitted=datetime.utcnow() - timedelta(days=1),
                ),
            ]
        )

        session.add_all(
            [
                Match(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    candidate_id=c1.id,
                    score=92,
                    tier="great_match",
                    reasons={"matched": [], "gaps": []},
                    missing_info=[],
                    flags=[],
                    matched_at=datetime.utcnow(),
                ),
                Match(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    candidate_id=c2.id,
                    score=40,
                    tier="red_flagged",
                    reasons={"matched": [], "gaps": []},
                    missing_info=["work authorization"],
                    flags=[{"color": "red", "note": "visa mismatch"}],
                    matched_at=datetime.utcnow(),
                ),
            ]
        )
        session.commit()
        return job.id


def test_dashboard_summary_aggregates_seeded_data(storage):
    job_id = _seed(storage)

    with storage.session() as session:
        summary = build_dashboard_summary(session)

    assert summary.kpis.active_jobs == 1
    assert summary.kpis.total_candidates == 2
    assert summary.kpis.matches_scored == 2
    # c2's match is both red-flagged AND missing info — that's one match
    # needing attention, not two (a prior bug summed the two counts instead
    # of counting each match once, double-counting matches that were both).
    assert summary.kpis.needs_attention == 1
    assert summary.red_flagged_count == 1

    tiers = {t.tier: t.count for t in summary.tier_distribution}
    assert tiers["great_match"] == 1
    assert tiers["poor_match"] == 0

    skill_labels = {s.label for s in summary.top_skills}
    assert "python" in skill_labels

    assert any(j.id == job_id and j.candidate_count == 2 for j in summary.jobs_snapshot)
    assert len(summary.needs_attention) == 1
    assert summary.needs_attention[0].reason == "Red-flagged"

    inflow_total_folder = sum(d.folder for d in summary.inflow_trend)
    inflow_total_email = sum(d.email for d in summary.inflow_trend)
    assert inflow_total_folder == 1
    assert inflow_total_email == 1


def test_needs_attention_kpi_counts_each_match_once(storage):
    """Three matches: red-flag-only, missing-info-only, and one that's
    both — needs_attention should be 3 (one per match), not 4 (which is
    what summing two separate counts would give)."""
    with storage.session() as session:
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", raw_text="Python")
        session.add(job)
        candidates = [
            Candidate(
                id=str(uuid.uuid4()),
                identity_fingerprint=f"email:kpi{i}@example.com",
                date_submitted=datetime.utcnow(),
            )
            for i in range(3)
        ]
        session.add_all(candidates)
        session.add_all(
            [
                Match(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    candidate_id=candidates[0].id,
                    score=30,
                    tier="red_flagged",
                    reasons={"matched": [], "gaps": []},
                    missing_info=[],
                    flags=[],
                    matched_at=datetime.utcnow(),
                ),
                Match(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    candidate_id=candidates[1].id,
                    score=60,
                    tier="average_match",
                    reasons={"matched": [], "gaps": []},
                    missing_info=["phone"],
                    flags=[],
                    matched_at=datetime.utcnow(),
                ),
                Match(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    candidate_id=candidates[2].id,
                    score=20,
                    tier="red_flagged",
                    reasons={"matched": [], "gaps": []},
                    missing_info=["visa status"],
                    flags=[],
                    matched_at=datetime.utcnow(),
                ),
            ]
        )
        session.commit()

        summary = build_dashboard_summary(session)

    assert summary.kpis.needs_attention == 3
    assert summary.red_flagged_count == 2


def test_recent_activity_describes_nameless_candidates_without_bare_added(storage):
    # A candidate with a blank name (thin/garbled resume) must not produce
    # the string "Added" with no name — f"Added {a} {b}".strip() only
    # strips the OUTSIDE of the string, so "Added  ".strip() -> "Added"
    # (still truthy) is the bug this guards against.
    with storage.session() as session:
        session.add(
            Candidate(
                id=str(uuid.uuid4()),
                identity_fingerprint="email:nameless@example.com",
                legal_first_name="",
                legal_last_name="",
                email="nameless@example.com",
                date_submitted=datetime.utcnow(),
            )
        )
        session.commit()

    with storage.session() as session:
        summary = build_dashboard_summary(session)

    descriptions = [a.description for a in summary.recent_activity]
    assert "Added" not in descriptions
    assert "Added a new candidate" in descriptions


def test_dashboard_summary_empty_state_has_no_errors(storage):
    with storage.session() as session:
        summary = build_dashboard_summary(session)

    assert summary.kpis.total_candidates == 0
    assert summary.needs_attention == []
    assert len(summary.inflow_trend) == 31  # 30 days + today


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("USE_MOCK", "true")

    from app.dependencies import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def test_dashboard_route_requires_auth(client):
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


def test_dashboard_route_returns_summary_when_authenticated(client):
    register = client.post(
        "/api/v1/auth/register", json={"email": "recruiter@example.com", "password": "correct-horse-battery"}
    )
    token = register.json()["token"]

    resp = client.get("/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kpis"]["total_candidates"] == 0
    assert "inflow_trend" in body
