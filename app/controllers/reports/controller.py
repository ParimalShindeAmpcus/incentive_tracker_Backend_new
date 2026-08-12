"""Reports HTTP routes — approved cycle final report."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.models.reports.schemas import ReportResponse, ReportTeamsResponse
from app.services.common.deps import CurrentUser, DbSession
from app.services.reports import reports_service

router = APIRouter(prefix="/reports")


@router.get("", response_model=ReportResponse)
def get_reports(
    db: DbSession,
    user: CurrentUser,
    division: Optional[str] = Query(None, description="Division code, e.g. nashik"),
    team: Optional[str] = Query(None, description="Team or coordinator name filter"),
    from_date: Optional[date] = Query(None, description="Inclusive lower bound (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="Inclusive upper bound (YYYY-MM-DD)"),
    approved_only: bool = Query(True, description="Only APPROVED cycles (final report)"),
) -> ReportResponse:
    """Final incentive report rows (approved-cycle Excel shape)."""
    _ = user
    return reports_service.get_report(
        db,
        division=None if not division or division == "ALL" else division,
        team=None if not team or team == "ALL" else team,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
    )


@router.get("/teams", response_model=ReportTeamsResponse)
def get_report_teams(
    db: DbSession,
    user: CurrentUser,
    division: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    approved_only: bool = Query(True),
) -> ReportTeamsResponse:
    """Distinct team / coordinator names for the Reports filter dropdown."""
    _ = user
    return reports_service.list_teams(
        db,
        division=None if not division or division == "ALL" else division,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
    )
