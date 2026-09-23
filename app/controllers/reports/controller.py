"""Reports HTTP routes — approved cycle final report."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.models.reports.schemas import (
    ReportCycleItem,
    ReportCyclesResponse,
    ReportEmployeesResponse,
    ReportHODsResponse,
    ReportMonthsResponse,
    ReportResponse,
    ReportTeamsResponse,
)
from app.services.common.deps import CurrentUser, DbSession
from app.services.reports import reports_service

router = APIRouter(prefix="/reports")


@router.get("", response_model=ReportResponse)
def get_reports(
    db: DbSession,
    user: CurrentUser,
    division: Optional[str] = Query(None, description="Division code, e.g. nashik"),
    cycle_id: Optional[int] = Query(None, description="Incentive cycle ID filter"),
    month: Optional[str] = Query(None, description="Incentive month filter (YYYY-MM)"),
    team: Optional[str] = Query(None, description="Team or coordinator name filter"),
    from_date: Optional[date] = Query(None, description="Inclusive lower bound (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="Inclusive upper bound (YYYY-MM-DD)"),
    approved_only: bool = Query(True, description="Only APPROVED cycles (final report)"),
    hod: Optional[str] = Query(None, description="HOD filter"),
    employee: Optional[str] = Query(None, description="Coordinator / candidate search"),
    coordinator: Optional[str] = Query(None, description="Coordinator exact/partial match"),
) -> ReportResponse:
    """Final incentive report rows (approved-cycle Excel shape)."""
    _ = user
    return reports_service.get_report(
        db,
        division=None if not division or division == "ALL" else division,
        cycle_id=cycle_id,
        month=None if not month or month == "ALL" else month,
        team=None if not team or team == "ALL" else team,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
        hod=None if not hod or hod == "ALL" else hod,
        employee_name=employee,
        coordinator=coordinator,
    )


@router.get("/cycles", response_model=ReportCyclesResponse)
def get_report_cycles(
    db: DbSession,
    user: CurrentUser,
    division: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
) -> ReportCyclesResponse:
    """Distinct incentive cycles available for Reports filter dropdown."""
    _ = user
    return reports_service.list_cycles(
        db,
        division=None if not division or division == "ALL" else division,
        month=None if not month or month == "ALL" else month,
    )


@router.get("/months", response_model=ReportMonthsResponse)
def get_report_months(
    db: DbSession,
    user: CurrentUser,
    division: Optional[str] = Query(None),
) -> ReportMonthsResponse:
    """Distinct incentive months available for Reports filter dropdown."""
    _ = user
    return reports_service.list_months(
        db,
        division=None if not division or division == "ALL" else division,
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


@router.get("/hods", response_model=ReportHODsResponse)
def get_report_hods(
    db: DbSession,
    user: CurrentUser,
    division: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    approved_only: bool = Query(True),
) -> ReportHODsResponse:
    """Distinct HOD names for the Reports filter dropdown."""
    _ = user
    hods = reports_service.list_hods(
        db,
        division=None if not division or division == "ALL" else division,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
    )
    return ReportHODsResponse(hods=hods)


@router.get("/employees", response_model=ReportEmployeesResponse)
def get_report_employees(
    db: DbSession,
    user: CurrentUser,
    division: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    approved_only: bool = Query(True),
    hod: Optional[str] = Query(None),
) -> ReportEmployeesResponse:
    """Distinct employee names for the Reports filter dropdown."""
    _ = user
    employees = reports_service.list_employees(
        db,
        division=None if not division or division == "ALL" else division,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
        hod=None if not hod or hod == "ALL" else hod,
    )
    return ReportEmployeesResponse(employees=employees)
