"""Personal landing page (post-login home) — one aggregated summary call."""

from fastapi import APIRouter, Depends

from app.dashboard.service import build_dashboard_summary
from app.dependencies import get_storage
from app.models.schemas import DashboardSummary
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        return build_dashboard_summary(session)
