"""Job Descriptions — the operational hub (2.1): search/paginate happen
client-side (frontend), no cap on how many a recruiter can create. Delete is
a soft-deactivate (Job.active=False) so existing Match/Criterion/SearchHistory
rows referencing the job stay intact — list_jobs only returns active ones."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.criteria.service import seed_builtin_criteria, seed_default_job_criteria
from app.dependencies import get_storage
from app.models.db import Job
from app.models.schemas import BulkDeleteJobsOut, BulkDeleteJobsRequest, JobCreate, JobOut
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        return list(
            session.execute(
                select(Job).where(Job.active.is_(True)).order_by(Job.created_at.desc())
            ).scalars()
        )


@router.post("", response_model=JobOut)
def create_job(payload: JobCreate, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        seed_builtin_criteria(session)
        job = Job(id=str(uuid.uuid4()), title=payload.title, company=payload.company, raw_text=payload.raw_text)
        session.add(job)
        session.commit()
        session.refresh(job)
        seed_default_job_criteria(session, job.id)
        # seed_default_job_criteria commits too, which expires this object's
        # already-loaded attributes again — refresh once more so the
        # response model can read them after the session closes below.
        session.refresh(job)
        return job


@router.delete("/{job_id}")
def deactivate_job(job_id: str, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.active = False
        session.commit()
        return {"status": "deactivated"}


@router.post("/bulk-delete", response_model=BulkDeleteJobsOut)
def bulk_deactivate_jobs(payload: BulkDeleteJobsRequest, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        jobs = list(session.execute(select(Job).where(Job.id.in_(payload.job_ids))).scalars())
        for job in jobs:
            job.active = False
        session.commit()
        return BulkDeleteJobsOut(deleted=len(jobs))
