"""Criteria library CRUD + per-job selection + rescan orchestration.

Adding/editing a criterion, or changing a job's selection of one, bumps the
job's criteria_version. The caller (routes/criteria.py) then offers the
recruiter a choice: re-run matching against already-ingested candidates
("existing_data" — fast, no re-ingest), or a full rescan that re-runs the
ingestors first ("full_rescan" — slower, picks up anything new too).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.criteria.builtin import BUILTIN_CRITERIA, CRITERION_FIELDS
from app.models.db import Criterion, Job, JobCriterion


def seed_builtin_criteria(session: Session) -> None:
    existing = session.execute(select(Criterion).where(Criterion.is_builtin.is_(True))).scalars().first()
    if existing:
        return
    for c in BUILTIN_CRITERIA:
        fields = {k: c[k] for k in CRITERION_FIELDS}
        session.add(Criterion(id=str(uuid.uuid4()), job_id=None, is_builtin=True, **fields))
    session.commit()


def seed_default_job_criteria(session: Session, job_id: str) -> None:
    """Pre-populate a newly-created job's criteria selection from the
    built-in defaults, so the checklist shows sensible values immediately
    instead of an empty state the recruiter has to build from scratch."""
    defaults_by_name = {c["name"]: c for c in BUILTIN_CRITERIA}
    builtins = session.execute(select(Criterion).where(Criterion.is_builtin.is_(True))).scalars()
    for criterion in builtins:
        default = defaults_by_name.get(criterion.name)
        if not default:
            continue
        session.add(
            JobCriterion(
                id=str(uuid.uuid4()),
                job_id=job_id,
                criterion_id=criterion.id,
                enabled=default["default_enabled"],
                value=default["default_value"],
            )
        )
    session.commit()


def list_criteria(session: Session, job_id: str | None) -> list[Criterion]:
    stmt = select(Criterion).where((Criterion.job_id.is_(None)) | (Criterion.job_id == job_id))
    return list(session.execute(stmt).scalars())


def add_criterion(
    session: Session,
    name: str,
    description: str,
    weight: float,
    job_id: str | None,
    field_type: str = "text",
    options: list[str] | None = None,
) -> Criterion:
    criterion = Criterion(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        weight=weight,
        job_id=job_id,
        is_builtin=False,
        field_type=field_type,
        options=options or [],
    )
    session.add(criterion)
    if job_id:
        job = session.get(Job, job_id)
        if job:
            job.criteria_version += 1
    session.commit()
    return criterion


def get_job_criteria(session: Session, job_id: str) -> list[tuple[Criterion, JobCriterion | None]]:
    """Every criterion in the library (global + this job's custom ones),
    paired with this job's selection row if one exists — the merged view
    the Job Descriptions page renders as a checklist of typed controls."""
    criteria = list_criteria(session, job_id)
    selections = {
        jc.criterion_id: jc
        for jc in session.execute(select(JobCriterion).where(JobCriterion.job_id == job_id)).scalars()
    }
    return [(c, selections.get(c.id)) for c in criteria]


def set_job_criterion(
    session: Session, job_id: str, criterion_id: str, enabled: bool, value: str
) -> JobCriterion:
    existing = session.execute(
        select(JobCriterion).where(JobCriterion.job_id == job_id, JobCriterion.criterion_id == criterion_id)
    ).scalar_one_or_none()

    if existing:
        existing.enabled = enabled
        existing.value = value
        selection = existing
    else:
        selection = JobCriterion(
            id=str(uuid.uuid4()), job_id=job_id, criterion_id=criterion_id, enabled=enabled, value=value
        )
        session.add(selection)

    job = session.get(Job, job_id)
    if job:
        job.criteria_version += 1
    session.commit()
    return selection
