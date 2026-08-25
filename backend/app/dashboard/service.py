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

from app.models.db import Candidate, EmailAccount, Job, Match, ResumeSource, SearchHistoryEntry
from app.models.enums import MatchTier
from app.models.schemas import (
    ActivityItem,
    AttentionItem,
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
NEEDS_ATTENTION_LIMIT = 8
RECENT_ACTIVITY_LIMIT = 10
ORDINAL_TIERS = [MatchTier.POOR, MatchTier.AVERAGE, MatchTier.GOOD, MatchTier.GREAT]


def _kpis(session: Session) -> tuple[DashboardKPIs, int]:
    active_jobs = session.execute(select(func.count()).select_from(Job).where(Job.active.is_(True))).scalar_one()
    total_candidates = session.execute(select(func.count()).select_from(Candidate)).scalar_one()
    matches_scored = session.execute(select(func.count()).select_from(Match)).scalar_one()

    # A single match can be both red-flagged AND missing info — summing two
    # separate counts double-counted it, so the KPI tile could show a bigger
    # number than the "Needs attention" list below ever could (that list
    # counts each match once, on the `or`). Count matches once instead.
    attention_rows = session.execute(select(Match.tier, Match.missing_info)).all()
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


def _inflow_trend(session: Session) -> list[InflowDay]:
    since = datetime.utcnow() - timedelta(days=INFLOW_DAYS)
    rows = session.execute(
        select(
            func.strftime("%Y-%m-%d", ResumeSource.date_submitted).label("day"),
            ResumeSource.origin,
            func.count(),
        )
        .where(ResumeSource.date_submitted >= since)
        .group_by("day", ResumeSource.origin)
    ).all()

    by_day: dict[str, dict[str, int]] = {}
    for day, origin, count in rows:
        by_day.setdefault(day, {"email": 0, "folder": 0})[origin] = count

    days = [(since + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(INFLOW_DAYS + 1)]
    return [InflowDay(date=d, email=by_day.get(d, {}).get("email", 0), folder=by_day.get(d, {}).get("folder", 0)) for d in days]


def _tier_distribution(session: Session) -> list[TierCount]:
    rows = session.execute(select(Match.tier, func.count()).group_by(Match.tier)).all()
    counts = {tier: count for tier, count in rows}
    return [TierCount(tier=t.value, count=counts.get(t.value, 0)) for t in ORDINAL_TIERS]


def _top_skills(session: Session) -> list[NamedCount]:
    skill_lists = session.execute(select(Candidate.skills)).scalars().all()
    counter: Counter[str] = Counter()
    for skills in skill_lists:
        counter.update(s.strip().lower() for s in (skills or []) if s.strip())
    return [NamedCount(label=skill, count=count) for skill, count in counter.most_common(TOP_SKILLS_LIMIT)]


def _visa_breakdown(session: Session) -> list[NamedCount]:
    rows = session.execute(select(Candidate.work_visa_status, func.count()).group_by(Candidate.work_visa_status)).all()
    rows = [(status, count) for status, count in rows if status and status != "unknown"]
    rows.sort(key=lambda r: r[1], reverse=True)
    return [NamedCount(label=status.replace("_", " ").upper(), count=count) for status, count in rows[:VISA_BREAKDOWN_LIMIT]]


def _jobs_snapshot(session: Session) -> list[JobSnapshot]:
    jobs = session.execute(select(Job).where(Job.active.is_(True)).order_by(Job.created_at.desc())).scalars().all()
    snapshots = []
    for job in jobs:
        agg = session.execute(
            select(func.count(func.distinct(Match.candidate_id)), func.max(Match.score), func.max(Match.matched_at)).where(
                Match.job_id == job.id
            )
        ).one()
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


def _needs_attention(session: Session) -> list[AttentionItem]:
    matches = session.execute(select(Match).order_by(Match.matched_at.desc()).limit(200)).scalars().all()
    items = []
    for m in matches:
        is_red_flag = m.tier == MatchTier.RED_FLAG.value
        has_missing_info = bool(m.missing_info)
        if not (is_red_flag or has_missing_info):
            continue
        candidate = session.get(Candidate, m.candidate_id)
        job = session.get(Job, m.job_id)
        if not candidate or not job:
            continue
        reason = "Red-flagged" if is_red_flag else f"Missing: {', '.join(m.missing_info[:2])}"
        items.append(
            AttentionItem(
                match_id=m.id,
                job_id=job.id,
                job_title=job.title,
                candidate_id=candidate.id,
                candidate_name=f"{candidate.legal_first_name} {candidate.legal_last_name}".strip() or candidate.email or "Unnamed candidate",
                reason=reason,
                tier=MatchTier(m.tier),
            )
        )
        if len(items) >= NEEDS_ATTENTION_LIMIT:
            break
    return items


def _recent_activity(session: Session) -> list[ActivityItem]:
    scans = session.execute(
        select(SearchHistoryEntry, Job.title)
        .join(Job, Job.id == SearchHistoryEntry.job_id)
        .order_by(SearchHistoryEntry.run_at.desc())
        .limit(RECENT_ACTIVITY_LIMIT)
    ).all()
    scan_items = [
        ActivityItem(
            type="scan",
            timestamp=entry.run_at,
            description=f"Matched {entry.candidate_count} candidate(s) against “{title}”",
            job_id=entry.job_id,
        )
        for entry, title in scans
    ]

    candidates = session.execute(
        select(Candidate).order_by(Candidate.created_at.desc()).limit(RECENT_ACTIVITY_LIMIT)
    ).scalars().all()
    candidate_items = []
    for c in candidates:
        full_name = f"{c.legal_first_name} {c.legal_last_name}".strip()
        candidate_items.append(
            ActivityItem(
                type="candidate",
                timestamp=c.created_at,
                description=f"Added {full_name}" if full_name else "Added a new candidate",
                candidate_id=c.id,
            )
        )

    merged = sorted(scan_items + candidate_items, key=lambda i: i.timestamp, reverse=True)
    return merged[:RECENT_ACTIVITY_LIMIT]


def build_dashboard_summary(session: Session) -> DashboardSummary:
    kpis, red_flagged_count = _kpis(session)
    return DashboardSummary(
        kpis=kpis,
        inflow_trend=_inflow_trend(session),
        tier_distribution=_tier_distribution(session),
        red_flagged_count=red_flagged_count,
        top_skills=_top_skills(session),
        visa_breakdown=_visa_breakdown(session),
        jobs_snapshot=_jobs_snapshot(session),
        needs_attention=_needs_attention(session),
        recent_activity=_recent_activity(session),
    )
