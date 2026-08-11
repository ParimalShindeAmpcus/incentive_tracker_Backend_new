"""Dashboard HTTP routes."""

from typing import Optional

from fastapi import APIRouter, Query

from app.models.dashboard.schemas import DashboardResponse
from app.services.common.deps import CurrentUser, DbSession
from app.services.dashboard import dashboard_service

router = APIRouter()


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    db: DbSession,
    user: CurrentUser,
    division: Optional[str] = Query(None, description="Division code filter, e.g. nashik"),
    year: Optional[str] = Query(None, description="YYYY or ALL"),
    month: Optional[str] = Query(None, description="MM or ALL"),
) -> DashboardResponse:
    """Aggregated dashboard payload for Divisions Hub + Recent Cycles."""
    _ = user  # auth required
    return dashboard_service.get_dashboard(
        db,
        division=None if not division or division == "ALL" else division,
        year=None if not year or year == "ALL" else year,
        month=None if not month or month == "ALL" else month,
    )
