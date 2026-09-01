import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.dashboard.service import build_dashboard_summary
from app.models.db import Candidate, IngestScanHistoryEntry, Job, Match, ResumeSource, SearchHistoryEntry


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
    assert len(summary.missing_info_breakdown) == 1
    assert summary.missing_info_breakdown[0].label == "work authorization"
    assert summary.missing_info_breakdown[0].count == 1

    inflow_total_folder = sum(d.folder for d in summary.inflow_trend)
    inflow_total_email = sum(d.email for d in summary.inflow_trend)
    assert inflow_total_folder == 1
    assert inflow_total_email == 1


def test_dashboard_pipeline_stage_distribution_zero_fills_and_counts(storage):
    job_id = _seed(storage)

    with storage.session() as session:
        matches = list(session.execute(select(Match).where(Match.job_id == job_id)).scalars())
        assert {m.pipeline_stage for m in matches} == {"sourced"}
        matches[0].pipeline_stage = "interviewing"
        session.commit()

        summary = build_dashboard_summary(session)

    stages = {s.stage: s.count for s in summary.pipeline_stage_distribution}
    assert stages == {
        "sourced": 1,
        "screened": 0,
        "submitted": 0,
        "interviewing": 1,
        "offer": 0,
        "placed": 0,
        "declined": 0,
    }


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


def test_needs_attention_kpi_counts_candidates_not_matches(storage):
    """A candidate red-flagged on two different jobs is one person needing
    attention, not two — the KPI must agree with storage.candidates_page's
    needs_attention filter (distinct candidates), which is what the tile
    links to. Counting matches instead let the tile disagree with its own
    linked page (QA: tile showed 103, the filtered list showed 97)."""
    with storage.session() as session:
        job1 = Job(id=str(uuid.uuid4()), title="Backend Engineer", raw_text="Python")
        job2 = Job(id=str(uuid.uuid4()), title="Platform Engineer", raw_text="Go")
        session.add_all([job1, job2])
        candidate = Candidate(
            id=str(uuid.uuid4()),
            identity_fingerprint="email:dual@example.com",
            date_submitted=datetime.utcnow(),
        )
        session.add(candidate)
        session.add_all(
            [
                Match(
                    id=str(uuid.uuid4()),
                    job_id=job1.id,
                    candidate_id=candidate.id,
                    score=20,
                    tier="red_flagged",
                    reasons={"matched": [], "gaps": []},
                    missing_info=[],
                    flags=[],
                    matched_at=datetime.utcnow(),
                ),
                Match(
                    id=str(uuid.uuid4()),
                    job_id=job2.id,
                    candidate_id=candidate.id,
                    score=25,
                    tier="red_flagged",
                    reasons={"matched": [], "gaps": []},
                    missing_info=[],
                    flags=[],
                    matched_at=datetime.utcnow(),
                ),
            ]
        )
        session.commit()

        summary = build_dashboard_summary(session)

    assert summary.kpis.needs_attention == 1


def test_recent_activity_shows_one_ingest_scan_summary_not_per_candidate_rows(storage):
    # A single scan can add hundreds of candidates at once — recent_activity
    # must surface one summary row for the scan (see IngestScanHistoryEntry),
    # not one row per candidate it created, which used to bury the actual
    # "what happened" summary under a wall of near-identical "Added X" rows.
    with storage.session() as session:
        for i in range(20):
            session.add(
                Candidate(
                    id=str(uuid.uuid4()),
                    identity_fingerprint=f"email:bulk{i}@example.com",
                    legal_first_name=f"Person{i}",
                    legal_last_name="Test",
                    email=f"bulk{i}@example.com",
                    date_submitted=datetime.utcnow(),
                )
            )
        session.add(
            IngestScanHistoryEntry(
                id=str(uuid.uuid4()),
                origin="email",
                source_label="me@example.com",
                resumes_found=22,
                candidates_created=20,
                candidates_updated=1,
                duplicates_skipped=1,
                error_count=0,
            )
        )
        session.commit()

    with storage.session() as session:
        summary = build_dashboard_summary(session)

    ingest_items = [a for a in summary.recent_activity if a.type == "ingest"]
    assert len(ingest_items) == 1
    assert ingest_items[0].description == "Scanned email (me@example.com) — 22 found, 20 new, 1 updated, 1 already seen"
    assert not any(a.type == "candidate" for a in summary.recent_activity)


def test_recent_activity_ingest_summary_reports_errors(storage):
    with storage.session() as session:
        session.add(
            IngestScanHistoryEntry(
                id=str(uuid.uuid4()),
                origin="folder",
                source_label="/resumes/2024",
                resumes_found=5,
                candidates_created=3,
                candidates_updated=0,
                duplicates_skipped=0,
                error_count=2,
            )
        )
        session.commit()

    with storage.session() as session:
        summary = build_dashboard_summary(session)

    ingest_items = [a for a in summary.recent_activity if a.type == "ingest"]
    assert len(ingest_items) == 1
    assert "2 error(s)" in ingest_items[0].description


def test_recent_activity_rescan_matched_entry_links_to_its_job(storage):
    # A "rescan matched"/"update matched" entry (match_rescan.py) belongs to
    # one job — Recent Activity should link straight to that job's Match
    # Results, not fall back to the generic All Candidates link every other
    # ingest entry (a plain scan, a maintenance run) uses.
    job_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(Job(id=job_id, title="Backend Engineer", raw_text="Python"))
        session.flush()
        session.add(
            IngestScanHistoryEntry(
                id=str(uuid.uuid4()),
                origin="email",
                source_label="rescan matched: Backend Engineer",
                resumes_found=5,
                candidates_created=0,
                candidates_updated=2,
                duplicates_skipped=3,
                error_count=0,
                job_id=job_id,
            )
        )
        session.commit()

    with storage.session() as session:
        summary = build_dashboard_summary(session)

    ingest_items = [a for a in summary.recent_activity if a.type == "ingest"]
    assert len(ingest_items) == 1
    assert ingest_items[0].job_id == job_id


def test_recent_activity_describes_maintenance_task_runs(storage):
    with storage.session() as session:
        session.add(
            IngestScanHistoryEntry(
                id=str(uuid.uuid4()),
                origin="maintenance",
                source_label="Backfill email links",
                resumes_found=607,
                candidates_created=590,
                candidates_updated=0,
                duplicates_skipped=17,
                error_count=0,
            )
        )
        session.commit()

    with storage.session() as session:
        summary = build_dashboard_summary(session)

    ingest_items = [a for a in summary.recent_activity if a.type == "ingest"]
    assert len(ingest_items) == 1
    assert ingest_items[0].description == "Ran “Backfill email links” — 607 checked, 590 new, 17 already seen"


def test_recent_activity_collapses_bulk_match_batch_into_one_expandable_entry(storage):
    # A Jobs-page "Match all" run writes one SearchHistoryEntry per job, all
    # sharing a batch_id (see stores/bulk-jobs-store.ts + routes/matches.py)
    # — recent_activity must collapse those into one row with the per-job
    # detail available as sub_items, not flood the feed with one line per
    # job in the batch.
    batch_id = str(uuid.uuid4())
    job1_id = str(uuid.uuid4())
    job2_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add_all(
            [
                Job(id=job1_id, title="Backend Engineer", raw_text="Python"),
                Job(id=job2_id, title="Frontend Engineer", raw_text="React"),
            ]
        )
        session.flush()
        session.add_all(
            [
                SearchHistoryEntry(id=str(uuid.uuid4()), job_id=job1_id, candidate_count=5, batch_id=batch_id),
                SearchHistoryEntry(id=str(uuid.uuid4()), job_id=job2_id, candidate_count=3, batch_id=batch_id),
                # An unrelated single-job run (no batch_id) stays its own row.
                SearchHistoryEntry(id=str(uuid.uuid4()), job_id=job1_id, candidate_count=1),
            ]
        )
        session.commit()

    with storage.session() as session:
        summary = build_dashboard_summary(session)

    scan_items = [a for a in summary.recent_activity if a.type == "scan"]
    assert len(scan_items) == 2  # one collapsed batch entry + one standalone entry

    batch_item = next(a for a in scan_items if a.sub_items)
    assert batch_item.description == "Matched 2 job(s) — 8 candidate match(es) total"
    assert len(batch_item.sub_items) == 2
    assert {s.job_id for s in batch_item.sub_items} == {job1_id, job2_id}

    standalone = next(a for a in scan_items if not a.sub_items)
    assert "1 candidate" in standalone.description


def test_dashboard_summary_empty_state_has_no_errors(storage):
    with storage.session() as session:
        summary = build_dashboard_summary(session)

    assert summary.kpis.total_candidates == 0
    assert summary.missing_info_breakdown == []
    assert len(summary.inflow_trend) == 31  # 30 days + today


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
