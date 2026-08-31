"""
Dashboard aggregation — one query pass per widget, assembled into a single
DashboardSummary so the frontend makes one call instead of N. Lives outside
routes/ (which stays thin) since this is genuinely aggregation logic, not
request/response plumbing.

Note: date bucketing uses SQLite's strftime, matching the current
LocalStorageBackend. A future Postgres-backed storage backend would need the
equivalent (to_char) here — this function, not the route, is the one place
that would change.
"""

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data_classification import candidate_id_condition, is_mock_source_condition
from app.models.db import Candidate, EmailAccount, IngestScanHistoryEntry, Job, Match, ResumeSource, SearchHistoryEntry
from app.models.enums import MatchTier
from app.models.schemas import (
    ActivityItem,
    DashboardKPIs,
    DashboardSummary,
    InflowDay,
    JobSnapshot,
    NamedCount,
    TierCount,
)

INFLOW_DAYS = 30
TOP_SKILLS_LIMIT = 8
VISA_BREAKDOWN_LIMIT = 8
MISSING_INFO_LIMIT = 8
RECENT_ACTIVITY_LIMIT = 10
ORDINAL_TIERS = [MatchTier.POOR, MatchTier.AVERAGE, MatchTier.GOOD, MatchTier.GREAT]


def _kpis(session: Session, data_mode: str) -> tuple[DashboardKPIs, int]:
    active_jobs = session.execute(select(func.count()).select_from(Job).where(Job.active.is_(True))).scalar_one()
    candidate_condition = candidate_id_condition(Candidate.id, data_mode)
    total_stmt = select(func.count()).select_from(Candidate)
    if candidate_condition is not None:
        total_stmt = total_stmt.where(candidate_condition)
    total_candidates = session.execute(total_stmt).scalar_one()

    match_condition = candidate_id_condition(Match.candidate_id, data_mode)
    matches_stmt = select(func.count()).select_from(Match)
    attention_stmt = select(Match.tier, Match.missing_info)
    if match_condition is not None:
        matches_stmt = matches_stmt.where(match_condition)
        attention_stmt = attention_stmt.where(match_condition)
    matches_scored = session.execute(matches_stmt).scalar_one()

    # A single match can be both red-flagged AND missing info — summing two
    # separate counts double-counted it, so the KPI tile could show a bigger
    # number than the "Needs attention" list below ever could (that list
    # counts each match once, on the `or`). Count matches once instead.
    attention_rows = session.execute(attention_stmt).all()
    red_flagged = sum(1 for tier, _ in attention_rows if tier == MatchTier.RED_FLAG.value)
    needs_attention = sum(1 for tier, missing_info in attention_rows if tier == MatchTier.RED_FLAG.value or missing_info)

    connected_mailboxes = session.execute(select(func.count()).select_from(EmailAccount)).scalar_one()
    connected_folders = session.execute(
        select(func.count(func.distinct(ResumeSource.source_ref))).where(ResumeSource.origin == "folder")
    ).scalar_one()

    kpis = DashboardKPIs(
        active_jobs=active_jobs,
        total_candidates=total_candidates,
        matches_scored=matches_scored,
        needs_attention=needs_attention,
        connected_sources=connected_mailboxes + connected_folders,
    )
    return kpis, red_flagged


def _inflow_trend(session: Session, data_mode: str) -> list[InflowDay]:
    since = datetime.utcnow() - timedelta(days=INFLOW_DAYS)
    stmt = select(
        func.strftime("%Y-%m-%d", ResumeSource.date_submitted).label("day"),
        ResumeSource.origin,
        func.count(),
    ).where(ResumeSource.date_submitted >= since)
    if data_mode == "real":
        stmt = stmt.where(~is_mock_source_condition())
    elif data_mode == "mock":
        stmt = stmt.where(is_mock_source_condition())
    rows = session.execute(stmt.group_by("day", ResumeSource.origin)).all()

    by_day: dict[str, dict[str, int]] = {}
    for day, origin, count in rows:
        by_day.setdefault(day, {"email": 0, "folder": 0})[origin] = count

    days = [(since + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(INFLOW_DAYS + 1)]
    return [InflowDay(date=d, email=by_day.get(d, {}).get("email", 0), folder=by_day.get(d, {}).get("folder", 0)) for d in days]


def _tier_distribution(session: Session, data_mode: str) -> list[TierCount]:
    stmt = select(Match.tier, func.count())
    match_condition = candidate_id_condition(Match.candidate_id, data_mode)
    if match_condition is not None:
        stmt = stmt.where(match_condition)
    rows = session.execute(stmt.group_by(Match.tier)).all()
    counts = {tier: count for tier, count in rows}
    return [TierCount(tier=t.value, count=counts.get(t.value, 0)) for t in ORDINAL_TIERS]


def _top_skills(session: Session, data_mode: str) -> list[NamedCount]:
    stmt = select(Candidate.skills)
    candidate_condition = candidate_id_condition(Candidate.id, data_mode)
    if candidate_condition is not None:
        stmt = stmt.where(candidate_condition)
    skill_lists = session.execute(stmt).scalars().all()
    counter: Counter[str] = Counter()
    for skills in skill_lists:
        counter.update(s.strip().lower() for s in (skills or []) if s.strip())
    return [NamedCount(label=skill, count=count) for skill, count in counter.most_common(TOP_SKILLS_LIMIT)]


def _visa_breakdown(session: Session, data_mode: str) -> list[NamedCount]:
    stmt = select(Candidate.work_visa_status, func.count())
    candidate_condition = candidate_id_condition(Candidate.id, data_mode)
    if candidate_condition is not None:
        stmt = stmt.where(candidate_condition)
    rows = session.execute(stmt.group_by(Candidate.work_visa_status)).all()
    rows = [(status, count) for status, count in rows if status and status != "unknown"]
    rows.sort(key=lambda r: r[1], reverse=True)
    return [NamedCount(label=status.replace("_", " ").upper(), count=count) for status, count in rows[:VISA_BREAKDOWN_LIMIT]]


def _jobs_snapshot(session: Session, data_mode: str) -> list[JobSnapshot]:
    jobs = session.execute(select(Job).where(Job.active.is_(True)).order_by(Job.created_at.desc())).scalars().all()
    match_condition = candidate_id_condition(Match.candidate_id, data_mode)
    snapshots = []
    for job in jobs:
        agg_stmt = select(
            func.count(func.distinct(Match.candidate_id)), func.max(Match.score), func.max(Match.matched_at)
        ).where(Match.job_id == job.id)
        if match_condition is not None:
            agg_stmt = agg_stmt.where(match_condition)
        agg = session.execute(agg_stmt).one()
        candidate_count, top_score, last_matched_at = agg
        snapshots.append(
            JobSnapshot(
                id=job.id,
                title=job.title,
                candidate_count=candidate_count or 0,
                top_score=top_score,
                last_matched_at=last_matched_at,
            )
        )
    return snapshots


def _missing_info_breakdown(session: Session, data_mode: str) -> list[NamedCount]:
    """How many distinct candidates are missing each kind of info, across
    any job match — backs the chart that replaced the old "Needs attention"
    list card (see project-log: that card duplicated what the All
    Candidates "Needs attention" filter now does better, with the actual
    candidate list one click away instead of a capped-at-8 preview).
    Counts by candidate, not by match, so a candidate matched against
    several jobs with the same gap isn't counted once per job."""
    stmt = select(Match.candidate_id, Match.missing_info)
    match_condition = candidate_id_condition(Match.candidate_id, data_mode)
    if match_condition is not None:
        stmt = stmt.where(match_condition)
    rows = session.execute(stmt).all()
    candidates_by_reason: dict[str, set[str]] = {}
    for candidate_id, missing in rows:
        for reason in missing or []:
            reason = reason.strip()
            if reason:
                candidates_by_reason.setdefault(reason, set()).add(candidate_id)
    ranked = sorted(candidates_by_reason.items(), key=lambda kv: len(kv[1]), reverse=True)
    return [NamedCount(label=reason, count=len(ids)) for reason, ids in ranked[:MISSING_INFO_LIMIT]]


def _ingest_description(entry: IngestScanHistoryEntry) -> str:
    parts = [f"{entry.candidates_created} new"]
    if entry.candidates_updated:
        parts.append(f"{entry.candidates_updated} updated")
    if entry.duplicates_skipped:
        parts.append(f"{entry.duplicates_skipped} already seen")
    if entry.error_count:
        parts.append(f"{entry.error_count} error(s)")

    if entry.origin == "maintenance":
        return f"Ran “{entry.source_label}” — {entry.resumes_found} checked, {', '.join(parts)}"
    source_kind = "email" if entry.origin == "email" else "folder"
    label = f" ({entry.source_label})" if entry.source_label else ""
    return f"Scanned {source_kind}{label} — {entry.resumes_found} found, {', '.join(parts)}"


# A Jobs-page bulk "Match all"/"Update matched (N)" run (see
# stores/bulk-jobs-store.ts) writes one history row per job, tagged with a
# shared batch_id — grabbing more raw rows than the final feed limit and
# collapsing same-batch rows into one entry (before truncating to
# RECENT_ACTIVITY_LIMIT) is what keeps a 20-job bulk run from flooding
# Recent Activity with 20 near-identical lines, the same problem
# IngestScanHistoryEntry itself was originally built to solve for a single
# scan's per-candidate rows.
_RAW_FETCH_LIMIT = 300


def _all_activity_items(session: Session) -> list[ActivityItem]:
    matching_runs = session.execute(
        select(SearchHistoryEntry, Job.title)
        .join(Job, Job.id == SearchHistoryEntry.job_id)
        .order_by(SearchHistoryEntry.run_at.desc())
        .limit(_RAW_FETCH_LIMIT)
    ).all()

    items: list[ActivityItem] = []
    matching_batches: dict[str, list[tuple[SearchHistoryEntry, str]]] = {}
    for entry, title in matching_runs:
        if entry.batch_id:
            matching_batches.setdefault(entry.batch_id, []).append((entry, title))
        else:
            items.append(
                ActivityItem(
                    type="scan",
                    timestamp=entry.run_at,
                    description=f"Matched {entry.candidate_count} candidate(s) against “{title}”",
                    job_id=entry.job_id,
                )
            )

    for rows in matching_batches.values():
        rows.sort(key=lambda r: r[0].run_at, reverse=True)
        sub_items = [
            ActivityItem(
                type="scan",
                timestamp=entry.run_at,
                description=f"Matched {entry.candidate_count} candidate(s) against “{title}”",
                job_id=entry.job_id,
            )
            for entry, title in rows
        ]
        total_candidates = sum(entry.candidate_count for entry, _ in rows)
        items.append(
            ActivityItem(
                type="scan",
                timestamp=rows[0][0].run_at,
                description=f"Matched {len(rows)} job(s) — {total_candidates} candidate match(es) total",
                sub_items=sub_items,
            )
        )

    # One row per completed ingest scan (folder or email) — e.g. "Scanned
    # Gmail (name@example.com) — 623 found, 607 new, 16 updated". Replaces
    # what used to be up to 10 near-identical "Added <candidate>" rows from
    # a single scan burying the actual summary — a scan that adds hundreds
    # of candidates at once used to make the whole feed just that one scan
    # repeated, with no indication a scan was even what happened.
    ingest_scans = session.execute(
        select(IngestScanHistoryEntry).order_by(IngestScanHistoryEntry.ran_at.desc()).limit(_RAW_FETCH_LIMIT)
    ).scalars().all()

    ingest_batches: dict[str, list[IngestScanHistoryEntry]] = {}
    for entry in ingest_scans:
        if entry.batch_id:
            ingest_batches.setdefault(entry.batch_id, []).append(entry)
        else:
            items.append(
                ActivityItem(
                    type="ingest", timestamp=entry.ran_at, description=_ingest_description(entry), job_id=entry.job_id or ""
                )
            )

    for rows in ingest_batches.values():
        rows.sort(key=lambda e: e.ran_at, reverse=True)
        sub_items = [
            ActivityItem(type="ingest", timestamp=e.ran_at, description=_ingest_description(e), job_id=e.job_id or "")
            for e in rows
        ]
        total_checked = sum(e.resumes_found for e in rows)
        total_updated = sum(e.candidates_updated for e in rows)
        items.append(
            ActivityItem(
                type="ingest",
                timestamp=rows[0].ran_at,
                description=f"Checked matched candidates for {len(rows)} job(s) — {total_checked} checked, {total_updated} updated",
                sub_items=sub_items,
            )
        )

    return sorted(items, key=lambda i: i.timestamp, reverse=True)


def _recent_activity(session: Session) -> list[ActivityItem]:
    return _all_activity_items(session)[:RECENT_ACTIVITY_LIMIT]


def recent_activity_page(session: Session, limit: int, offset: int) -> tuple[list[ActivityItem], int]:
    """Paginated view of the same feed the Dashboard's Recent Activity
    summarizes to its top 10 — for the "see more activity" page, which
    needs to page back through everything, not just the glanceable recent
    slice. `total` reflects everything within _RAW_FETCH_LIMIT, the same
    cap _all_activity_items already applies per source table."""
    items = _all_activity_items(session)
    return items[offset : offset + limit], len(items)


def build_dashboard_summary(session: Session, data_mode: str = "all") -> DashboardSummary:
    # recent_activity is deliberately left unfiltered — it's a log of scans
    # and maintenance runs, not a candidate-derived widget, and a scan's own
    # description already says what it touched (email/folder/maintenance).
    kpis, red_flagged_count = _kpis(session, data_mode)
    return DashboardSummary(
        kpis=kpis,
        inflow_trend=_inflow_trend(session, data_mode),
        tier_distribution=_tier_distribution(session, data_mode),
        red_flagged_count=red_flagged_count,
        top_skills=_top_skills(session, data_mode),
        visa_breakdown=_visa_breakdown(session, data_mode),
        jobs_snapshot=_jobs_snapshot(session, data_mode),
        missing_info_breakdown=_missing_info_breakdown(session, data_mode),
        recent_activity=_recent_activity(session),
    )
