"""Criteria tab (requirement 5) — built-in + custom criteria, rescan trigger."""

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.criteria.service import add_criterion, get_job_criteria, list_criteria, seed_builtin_criteria, set_job_criterion
from app.dependencies import get_llm_client, get_settings, get_storage
from app.matching.llm_client import LLMClient
from app.models.db import Criterion, Job
from app.models.schemas import CriterionIn, CriterionOut, JobCriterionIn, JobCriterionOut, RescanRequest
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/criteria", tags=["criteria"])


@router.get("", response_model=list[CriterionOut])
def get_criteria(job_id: str | None = None, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        seed_builtin_criteria(session)
        return list(list_criteria(session, job_id))


@router.post("", response_model=CriterionOut)
def create_criterion(payload: CriterionIn, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        return add_criterion(
            session,
            payload.name,
            payload.description,
            payload.weight,
            payload.job_id,
            payload.field_type,
            payload.options,
        )


@router.get("/for-job/{job_id}", response_model=list[JobCriterionOut])
def get_criteria_for_job(job_id: str, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        seed_builtin_criteria(session)
        pairs = get_job_criteria(session, job_id)
        return [
            JobCriterionOut(criterion=criterion, enabled=selection.enabled if selection else False, value=selection.value if selection else "")
            for criterion, selection in pairs
        ]


@router.put("/for-job/{job_id}/{criterion_id}", response_model=JobCriterionOut)
def set_criterion_for_job(
    job_id: str, criterion_id: str, payload: JobCriterionIn, storage: BaseStorageBackend = Depends(get_storage)
):
    with storage.session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        criterion = session.get(Criterion, criterion_id)
        if not criterion:
            raise HTTPException(404, "Criterion not found")
        selection = set_job_criterion(session, job_id, criterion_id, payload.enabled, payload.value)
        return JobCriterionOut(criterion=criterion, enabled=selection.enabled, value=selection.value)


@router.post("/rescan")
async def rescan(
    payload: RescanRequest,
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    """'existing_data' re-runs matching over already-ingested candidates only
    (fast). 'full_rescan' is a hint to the frontend to re-trigger /scan/*
    first, then re-run matching — kept as two explicit steps so the recruiter
    sees ingestion progress separately from matching progress."""
    with storage.session() as session:
        job = session.get(Job, payload.job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if payload.mode not in ("existing_data", "full_rescan"):
            raise HTTPException(400, "mode must be 'existing_data' or 'full_rescan'")
        return {"job_id": payload.job_id, "mode": payload.mode, "next_step": "POST /api/v1/matches/run/{job_id}"}
