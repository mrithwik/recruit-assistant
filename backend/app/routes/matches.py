"""Candidate Results tab (2.5) — run matching for a job, list/filter results,
top-N selection, and green/red flag toggling."""

import asyncio
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.config import Settings
from app.data_classification import candidate_id_condition
from app.dependencies import get_llm_client, get_settings, get_storage
from app.matching.concurrency import bounded_gather
from app.matching.llm_client import LLMClient
from app.matching.matcher import match_job_against_pool, score_to_tier
from app.models.db import Candidate, Job, Match, SearchHistoryEntry
from app.models.schemas import (
    FlagIn,
    JobMatchSummary,
    MatchListOut,
    MatchOut,
    MatchReasons,
    MatchSummaryItem,
    PipelineStageIn,
    ScanJobOut,
    ScanResult,
)
from app.routes.candidates import _batch_email_links, _batch_origins, _to_out
from app.scanning.job_registry import ScanAlreadyRunningError, complete_job, create_job, fail_job, is_cancel_requested
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


def _job_out(job) -> ScanJobOut:
    return ScanJobOut(
        id=job.id,
        status=job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result=job.result,
        progress=job.progress,
        error=job.error,
        cancelled=job.cancelled,
    )


def _match_to_out(match: Match, candidate: Candidate, origins: list[str], email_link: str = "") -> MatchOut:
    return MatchOut(
        id=match.id,
        job_id=match.job_id,
        candidate=_to_out(candidate, origins, email_link),
        score=match.score,
        tier=match.tier,
        pipeline_stage=match.pipeline_stage,
        reasons=MatchReasons(**match.reasons) if match.reasons else MatchReasons(),
        missing_info=match.missing_info,
        flags=match.flags,
        judge_notes=match.judge_notes,
        criteria_version=match.criteria_version,
        matched_at=match.matched_at,
    )


async def _embedding_for(llm: LLMClient, model: str, candidate: Candidate) -> tuple[str, list[float]]:
    resume_text = candidate.raw_parsed_profile.get("raw_text", "") if candidate.raw_parsed_profile else ""
    embedding = await llm.embed(model, resume_text or candidate.semantic_summary)
    return candidate.id, embedding


@router.post("/run/{job_id}", response_model=ScanJobOut, status_code=202)
async def run_matching(
    job_id: str,
    top_n: int = Query(20, ge=1, le=200),
    data_mode: str = Query("all", description="'all', 'real', or 'mock' — restricts the candidate pool matched against"),
    batch_id: str | None = Query(None, description="Groups this run with others in the same bulk operation for Recent Activity"),
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    """Runs as a background job (same job_registry every scan/rescan uses)
    rather than blocking the request for the whole run — a real candidate
    pool + judge pass can take long enough that holding one HTTP connection
    open the whole time risks a browser/proxy timeout, and (the reason this
    changed from a synchronous call) gives the frontend a job id to poll,
    so "Run matching" survives a tab switch, a refresh, or a logout/login —
    the same guarantee scans and rescans already had. The actual match rows
    land in the DB as soon as they're scored; the client re-fetches them via
    GET /matches/{job_id} once the job reports "completed" rather than the
    job's own result carrying the full match list."""
    with storage.session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job_raw_text = job.raw_text
        job_criteria_version = job.criteria_version

    scope_key = f"run_matching:{job_id}"
    try:
        rjob = create_job(scope_key)
    except ScanAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc

    async def _run() -> None:
        try:
            with storage.session() as session:
                pool_stmt = select(Candidate)
                candidate_condition = candidate_id_condition(Candidate.id, data_mode)
                if candidate_condition is not None:
                    pool_stmt = pool_stmt.where(candidate_condition)
                candidates = list(session.execute(pool_stmt).scalars())
                if not candidates:
                    complete_job(
                        rjob.id,
                        ScanResult(resumes_found=0, candidates_created=0, candidates_updated=0, duplicates_skipped=0),
                    )
                    return

                job_embedding = await llm.embed(settings.embedding_model, job_raw_text)

                # Candidates ingested after the embedding-cache change (see
                # ingest_service.py) already carry `embedding` — reuse it
                # instead of re-embedding the whole pool on every single "Run
                # matching" click, which used to be the dominant cost at real
                # volume (10k candidates = 10k sequential embed calls, every
                # run). Only candidates missing one get embedded here,
                # concurrently.
                needs_embedding = [c for c in candidates if not c.embedding]
                if needs_embedding:
                    computed = await bounded_gather(
                        needs_embedding,
                        lambda c: _embedding_for(llm, settings.embedding_model, c),
                        settings.max_concurrent_llm_calls,
                    )
                    embedding_by_id = dict(computed)
                    for c in needs_embedding:
                        c.embedding = embedding_by_id[c.id]
                    session.flush()

                # Cancellation can only be checked between phases, not mid
                # concurrent-gather (match_job_against_pool scores the whole
                # pool in one bounded_gather pass) — this is the last point
                # before that expensive phase starts, so a cancel requested
                # during embedding still takes effect instead of running the
                # full scoring pass anyway.
                if is_cancel_requested(rjob.id):
                    complete_job(
                        rjob.id,
                        ScanResult(resumes_found=len(candidates), candidates_created=0, candidates_updated=0, duplicates_skipped=0),
                    )
                    return

                pool = [
                    {
                        "id": c.id,
                        "embedding": c.embedding,
                        "resume_text": c.raw_parsed_profile.get("raw_text", "") if c.raw_parsed_profile else "",
                        "profile": _profile_from_candidate(c),
                        "summary": c.semantic_summary,
                    }
                    for c in candidates
                ]

                results = await match_job_against_pool(
                    llm=llm,
                    triage_model=settings.llm_triage_model,
                    scoring_model=settings.llm_scoring_model,
                    judge_model=settings.llm_judge_model,
                    job_text=job_raw_text,
                    job_embedding=job_embedding,
                    candidate_pool=pool,
                    top_n=top_n,
                    max_concurrent=settings.max_concurrent_llm_calls,
                )

                candidates_by_id = {c.id: c for c in candidates}
                matched_count = 0
                for r in results[:top_n]:
                    tier = score_to_tier(r["score"], has_red_flag=False)
                    match = Match(
                        id=str(uuid.uuid4()),
                        job_id=job_id,
                        candidate_id=r["candidate_id"],
                        score=r["score"],
                        tier=tier.value,
                        reasons={"matched": r["matched"], "gaps": r["gaps"]},
                        missing_info=r["missing_info"],
                        flags=[],
                        judge_notes=r["judge_notes"],
                        criteria_version=job_criteria_version,
                        matched_at=datetime.utcnow(),
                    )
                    session.add(match)
                    matched_count += 1

                storage.record_search_history(
                    session,
                    SearchHistoryEntry(
                        id=str(uuid.uuid4()),
                        job_id=job_id,
                        candidate_count=matched_count,
                        criteria_version=job_criteria_version,
                        sources_scanned={"note": f"matched against candidate pool at run time (data_mode={data_mode})"},
                        batch_id=batch_id,
                    ),
                )
                session.commit()

            complete_job(
                rjob.id,
                ScanResult(
                    resumes_found=len(candidates),
                    candidates_created=matched_count,
                    candidates_updated=0,
                    duplicates_skipped=0,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced via job status, not raised into a dead background task
            fail_job(rjob.id, str(exc))

    rjob.task = asyncio.create_task(_run())
    return _job_out(rjob)


@router.get("/summary/{job_id}", response_model=JobMatchSummary)
def get_match_summary(job_id: str, storage: BaseStorageBackend = Depends(get_storage)):
    """Lightweight rollup for the Jobs page — tier counts + top 3 candidates,
    so a recruiter can see how a job's results stand without leaving the
    Job Descriptions page (see requirement: results per job at a glance)."""
    with storage.session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        matches = list(
            session.execute(
                select(Match).where(Match.job_id == job_id).order_by(Match.score.desc())
            ).scalars()
        )
        tier_counts: dict[str, int] = {}
        for m in matches:
            tier_counts[m.tier] = tier_counts.get(m.tier, 0) + 1

        top = matches[:3]
        top_candidates = []
        for m in top:
            candidate = session.get(Candidate, m.candidate_id)
            name = (
                f"{candidate.legal_first_name} {candidate.legal_last_name}".strip()
                or candidate.email
                or "Unnamed candidate"
            ) if candidate else "Unknown"
            top_candidates.append(
                MatchSummaryItem(
                    match_id=m.id,
                    job_id=job_id,
                    job_title=job.title,
                    candidate_id=m.candidate_id,
                    candidate_name=name,
                    score=m.score,
                    tier=m.tier,
                    pipeline_stage=m.pipeline_stage,
                    matched_at=m.matched_at,
                )
            )
        last_matched_at = max((m.matched_at for m in matches), default=None)
        return JobMatchSummary(
            job_id=job_id,
            total_matches=len(matches),
            tier_counts=tier_counts,
            top_candidates=top_candidates,
            last_matched_at=last_matched_at,
        )


@router.get("/{job_id}", response_model=MatchListOut)
def list_matches(
    job_id: str,
    top_n: int = Query(20, ge=1, le=200),
    data_mode: str = Query("all", description="'all', 'real', or 'mock'"),
    storage: BaseStorageBackend = Depends(get_storage),
):
    start_time = time.monotonic()
    with storage.session() as session:
        match_stmt = select(Match).where(Match.job_id == job_id)
        data_mode_condition = candidate_id_condition(Match.candidate_id, data_mode)
        if data_mode_condition is not None:
            match_stmt = match_stmt.where(data_mode_condition)
        matches = list(
            session.execute(match_stmt.order_by(Match.score.desc()).limit(top_n)).scalars()
        )
        candidate_ids = [m.candidate_id for m in matches]
        candidates_by_id = {
            c.id: c for c in session.execute(select(Candidate).where(Candidate.id.in_(candidate_ids))).scalars()
        }
        origins_by_candidate = _batch_origins(session, candidate_ids)
        email_links_by_candidate = _batch_email_links(session, candidate_ids)
        out = [
            _match_to_out(
                m,
                candidates_by_id[m.candidate_id],
                origins_by_candidate.get(m.candidate_id, []),
                email_links_by_candidate.get(m.candidate_id, ""),
            )
            for m in matches
            if m.candidate_id in candidates_by_id
        ]
        return MatchListOut(matches=out, elapsed_seconds=round(time.monotonic() - start_time, 3))


@router.post("/{match_id}/flag", response_model=MatchOut)
def add_flag(match_id: str, flag: FlagIn, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        match = session.get(Match, match_id)
        if not match:
            raise HTTPException(404, "Match not found")
        match.flags = [*match.flags, {"color": flag.color, "note": flag.note}]
        if flag.color == "red":
            from app.models.enums import MatchTier

            match.tier = MatchTier.RED_FLAG.value
        session.commit()
        candidate = session.get(Candidate, match.candidate_id)
        origins = _batch_origins(session, [candidate.id]).get(candidate.id, [])
        email_link = _batch_email_links(session, [candidate.id]).get(candidate.id, "")
        return _match_to_out(match, candidate, origins, email_link)


@router.post("/{match_id}/stage", response_model=MatchOut)
def update_pipeline_stage(match_id: str, stage_in: PipelineStageIn, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        match = session.get(Match, match_id)
        if not match:
            raise HTTPException(404, "Match not found")
        match.pipeline_stage = stage_in.stage.value
        session.commit()
        candidate = session.get(Candidate, match.candidate_id)
        origins = _batch_origins(session, [candidate.id]).get(candidate.id, [])
        email_link = _batch_email_links(session, [candidate.id]).get(candidate.id, "")
        return _match_to_out(match, candidate, origins, email_link)


def _profile_from_candidate(c: Candidate):
    from app.models.enums import EmploymentStatus, WorkVisaStatus
    from app.models.schemas import CandidateProfile

    return CandidateProfile(
        legal_first_name=c.legal_first_name,
        legal_middle_name=c.legal_middle_name,
        legal_last_name=c.legal_last_name,
        email=c.email,
        phone=c.phone,
        employment_status=EmploymentStatus(c.employment_status) if c.employment_status else EmploymentStatus.UNKNOWN,
        work_visa_status=WorkVisaStatus(c.work_visa_status) if c.work_visa_status else WorkVisaStatus.UNKNOWN,
        skills=c.skills,
        experience_years=c.experience_years,
        education=c.education,
        raw_text=(c.raw_parsed_profile or {}).get("raw_text", ""),
    )
