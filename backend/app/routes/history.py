"""Search History tab (2.7)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.dependencies import get_storage
from app.models.db import SearchHistoryEntry
from app.models.schemas import SearchHistoryOut
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/history", tags=["history"])


@router.get("", response_model=list[SearchHistoryOut])
def list_history(job_id: str | None = None, storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        stmt = select(SearchHistoryEntry).order_by(SearchHistoryEntry.run_at.desc())
        if job_id:
            stmt = stmt.where(SearchHistoryEntry.job_id == job_id)
        return list(session.execute(stmt).scalars())
