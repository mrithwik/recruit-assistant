"""Candidate lookup, filterable by date submitted / source — backs the
date-range filtering in Candidate Results (2.5) regardless of origin."""

import time
from datetime import datetime

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.dependencies import get_storage
from app.models.db import Candidate, Job, Match, ResumeSource
from app.models.enums import EmploymentStatus, WorkVisaStatus
from app.models.schemas import (
    CandidateDetailOut,
    CandidateFacetsOut,
    CandidateListOut,
    CandidateMatchDetail,
    CandidateOut,
    MatchReasons,
    ResumeSourceOut,
)
from app.scanning.parser import extract_text
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])


def _batch_origins(session, candidate_ids: list[str]) -> dict[str, list[str]]:
    """One query for every candidate's origins instead of one query per
    candidate — the previous version ran N+1 queries (one per row), which
    was the main reason the All Candidates page was slow at real volume."""
    if not candidate_ids:
        return {}
    origins: dict[str, list[str]] = {}
    rows = session.execute(
        select(ResumeSource.candidate_id, ResumeSource.origin).where(ResumeSource.candidate_id.in_(candidate_ids))
    ).all()
    for candidate_id, origin in rows:
        origins.setdefault(candidate_id, []).append(origin)
    return origins


def _batch_email_links(session, candidate_ids: list[str]) -> dict[str, str]:
    """Most recent non-blank email_link per candidate — one query for the
    whole page rather than one per candidate, same reasoning as
    _batch_origins. A candidate can have several email sources (re-applied
    over time); the most recent one is the most useful deep link to surface."""
    if not candidate_ids:
        return {}
    rows = session.execute(
        select(ResumeSource.candidate_id, ResumeSource.email_link, ResumeSource.date_submitted)
        .where(ResumeSource.candidate_id.in_(candidate_ids), ResumeSource.email_link != "")
        .order_by(ResumeSource.date_submitted.desc())
    ).all()
    links: dict[str, str] = {}
    for candidate_id, email_link, _date in rows:
        links.setdefault(candidate_id, email_link)  # first hit per id is the most recent, rows are date-desc
    return links


def _to_out(candidate: Candidate, origins: list[str], email_link: str = "") -> CandidateOut:
    # A candidate can have many ResumeSource rows per origin (re-submitted
    # several times by email, say) — dedupe here so "sources" reads as which
    # channels this candidate was seen through, not a tally of every row.
    distinct_origins = sorted(set(origins))
    return CandidateOut(
        id=candidate.id,
        legal_first_name=candidate.legal_first_name,
        legal_middle_name=candidate.legal_middle_name,
        legal_last_name=candidate.legal_last_name,
        email=candidate.email,
        phone=candidate.phone,
        employment_status=candidate.employment_status,
        work_visa_status=candidate.work_visa_status,
        skills=candidate.skills,
        experience_years=candidate.experience_years,
        education=candidate.education,
        semantic_summary=candidate.semantic_summary,
        date_submitted=candidate.date_submitted,
        primary_file_path=candidate.primary_file_path,
        linkedin_url=candidate.linkedin_url,
        github_url=candidate.github_url,
        portfolio_url=candidate.portfolio_url,
        sources=distinct_origins,
        history=candidate.history,
        email_link=email_link,
    )


@router.get("", response_model=CandidateListOut)
def list_candidates(
    date_start: datetime | None = Query(None),
    date_end: datetime | None = Query(None),
    source: str | None = Query(None, description="'email' or 'folder', omit for both"),
    q: str | None = Query(None, description="search name, email, or skill"),
    sort: str = Query("recent", description="recent | oldest | name_asc | name_desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    skill: list[str] | None = Query(None, description="repeatable; candidate must have at least one"),
    employment_status: list[str] | None = Query(None, description="repeatable; any of"),
    work_visa_status: list[str] | None = Query(None, description="repeatable; any of"),
    experience_min: float | None = Query(None, ge=0),
    experience_max: float | None = Query(None, ge=0),
    storage: BaseStorageBackend = Depends(get_storage),
):
    start_time = time.monotonic()
    with storage.session() as session:
        candidates, total = storage.candidates_page(
            session,
            date_start,
            date_end,
            source,
            q,
            sort,
            limit,
            offset,
            skills=skill,
            employment_statuses=employment_status,
            work_visa_statuses=work_visa_status,
            experience_min=experience_min,
            experience_max=experience_max,
        )
        candidate_ids = [c.id for c in candidates]
        origins_by_candidate = _batch_origins(session, candidate_ids)
        email_links_by_candidate = _batch_email_links(session, candidate_ids)
        out = [_to_out(c, origins_by_candidate.get(c.id, []), email_links_by_candidate.get(c.id, "")) for c in candidates]
        return CandidateListOut(candidates=out, total=total, elapsed_seconds=round(time.monotonic() - start_time, 3))


@router.get("/facets", response_model=CandidateFacetsOut)
def get_candidate_facets(storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        skills, max_experience = storage.candidate_facets(session)
        return CandidateFacetsOut(
            skills=skills,
            employment_statuses=[s.value for s in EmploymentStatus],
            work_visa_statuses=[s.value for s in WorkVisaStatus],
            experience_years_max=max_experience,
        )


@router.get("/{candidate_id}", response_model=CandidateDetailOut)
def get_candidate(candidate_id: str, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            raise HTTPException(404, "Candidate not found")
        origins = _batch_origins(session, [candidate.id]).get(candidate.id, [])
        email_link = _batch_email_links(session, [candidate.id]).get(candidate.id, "")
        base = _to_out(candidate, origins, email_link)

        matches = list(
            session.execute(
                select(Match, Job.title)
                .join(Job, Job.id == Match.job_id)
                .where(Match.candidate_id == candidate_id)
                .order_by(Match.matched_at.desc())
            ).all()
        )
        full_name = f"{candidate.legal_first_name} {candidate.legal_last_name}".strip() or candidate.email
        match_details = [
            CandidateMatchDetail(
                match_id=m.id,
                job_id=m.job_id,
                job_title=title,
                candidate_id=candidate_id,
                candidate_name=full_name,
                score=m.score,
                tier=m.tier,
                matched_at=m.matched_at,
                reasons=MatchReasons(**m.reasons) if m.reasons else MatchReasons(),
                missing_info=m.missing_info,
                flags=m.flags,
                judge_notes=m.judge_notes,
            )
            for m, title in matches
        ]
        return CandidateDetailOut(**base.model_dump(), matches=match_details)


@router.get("/{candidate_id}/sources", response_model=list[ResumeSourceOut])
def list_candidate_sources(candidate_id: str, storage: BaseStorageBackend = Depends(get_storage)):
    """Every submission (email or folder) that fed this candidate — the
    'clickable link to their email/resume text' list on the detail page."""
    with storage.session() as session:
        sources = list(
            session.execute(
                select(ResumeSource)
                .where(ResumeSource.candidate_id == candidate_id)
                .order_by(ResumeSource.date_submitted.desc())
            ).scalars()
        )
        return [
            ResumeSourceOut(
                id=s.id,
                origin=s.origin,
                source_ref=s.source_ref,
                date_submitted=s.date_submitted,
                additional_attachments=s.additional_attachments,
                email_link=s.email_link,
            )
            for s in sources
        ]


@router.get("/{candidate_id}/sources/{source_id}/text")
def get_candidate_source_text(
    candidate_id: str, source_id: str, storage: BaseStorageBackend = Depends(get_storage)
):
    """Reads back the mirrored file for one submission — for email-origin
    sources this is the message body (a follow-up note) or the resume
    attachment text itself, whichever was ingested; for folder-origin
    sources it's the resume file's extracted text."""
    with storage.session() as session:
        source = session.get(ResumeSource, source_id)
        if not source or source.candidate_id != candidate_id:
            raise HTTPException(404, "Source not found")
        path = Path(source.file_path)
        if not path.exists():
            raise HTTPException(404, "Source file no longer on disk")
        text = extract_text(path.read_bytes(), path.name)
        return {
            "origin": source.origin,
            "source_ref": source.source_ref,
            "date_submitted": source.date_submitted,
            "text": text or "(no extractable text)",
        }
