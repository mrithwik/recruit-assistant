"""Personal landing page (post-login home) — one aggregated summary call."""

from fastapi import APIRouter, Depends, Query

from app.dashboard.service import build_dashboard_summary, recent_activity_page
from app.dependencies import get_storage
from app.models.schemas import ActivityLogPage, DashboardSummary
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    data_mode: str = Query("all", description="'all', 'real', or 'mock'"),
    storage: BaseStorageBackend = Depends(get_storage),
):
    with storage.session() as session:
        return build_dashboard_summary(session, data_mode=data_mode)


@router.get("/activity", response_model=ActivityLogPage)
def get_activity_log(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    storage: BaseStorageBackend = Depends(get_storage),
):
    """Paginated version of the Dashboard's Recent Activity, which only
    ever shows its latest 10. Backs the "see more activity" page-through UI
    on the Dashboard's Recent Activity card."""
    with storage.session() as session:
        items, total = recent_activity_page(session, limit=limit, offset=offset)
        return ActivityLogPage(items=items, total=total)
