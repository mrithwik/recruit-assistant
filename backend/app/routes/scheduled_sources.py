"""CRUD for opt-in nightly auto-scan sources (the scheduler toggle on the
Scan Sources page). This is deliberately separate from /scan — adding a row
here never runs a scan itself, it only tells the opt-in scheduler
(app/scheduler/) to include this source in its next nightly run, if the
scheduler is even enabled (SCHEDULER_ENABLED, off by default)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.dependencies import get_storage
from app.models.db import ScheduledSource
from app.models.schemas import ScheduledSourceIn, ScheduledSourceOut
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/scheduled-sources", tags=["scheduled-sources"])


@router.get("", response_model=list[ScheduledSourceOut])
def list_scheduled_sources(storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        return list(session.execute(select(ScheduledSource)).scalars())


@router.post("", response_model=ScheduledSourceOut)
def add_scheduled_source(payload: ScheduledSourceIn, storage: BaseStorageBackend = Depends(get_storage)):
    if payload.kind not in ("folder", "email_account"):
        raise HTTPException(400, "kind must be 'folder' or 'email_account'")
    with storage.session() as session:
        existing = session.execute(
            select(ScheduledSource).where(ScheduledSource.kind == payload.kind, ScheduledSource.ref == payload.ref)
        ).scalar_one_or_none()
        if existing:
            return existing
        source = ScheduledSource(
            id=str(uuid.uuid4()),
            kind=payload.kind,
            ref=payload.ref,
            include_subfolders=payload.include_subfolders,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        return source


@router.delete("/{source_id}")
def remove_scheduled_source(source_id: str, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        source = session.get(ScheduledSource, source_id)
        if not source:
            raise HTTPException(404, "Scheduled source not found")
        session.delete(source)
        session.commit()
    return {"status": "removed"}
