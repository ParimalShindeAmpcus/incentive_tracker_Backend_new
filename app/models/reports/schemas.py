"""Reports DTOs — approved-cycle Excel layout (13 columns)."""

from decimal import Decimal
from typing import List, Optional, Union

from pydantic import BaseModel


class ReportRowOut(BaseModel):
    """One report row. Frontend maps these fields to approved-cycle Excel headers."""

    coordinator_name: str
    coordinator_type: str
    candidate_id: str
    candidate_name: str
    start_date: str
    month: str
    contract_type: str
    margin_finder_fees: Union[Decimal, str, float, int]
    hours_placements: Union[Decimal, float, int]
    incentive_amount_inr: Union[Decimal, float, int]
    incentive_type: str
    candidate_source: str
    team: str
    division: Optional[str] = None
    cycle_id: Optional[int] = None
    cycle_name: Optional[str] = None
    incentive_month: Optional[str] = None
    metric_type: str = "HOURS"
    monthly_hours: Optional[Union[Decimal, float, int]] = None
    monthly_days: Optional[int] = None
    validation_summary: Optional[str] = None
    rule_applied: Optional[str] = None


class ReportResponse(BaseModel):
    rows: List[ReportRowOut]
    total_rows: int
    total_incentive: Decimal


class ReportTeamsResponse(BaseModel):
    teams: List[str]


class ReportHODsResponse(BaseModel):
    hods: List[str]


class ReportEmployeesResponse(BaseModel):
    employees: List[str]


class ReportCycleItem(BaseModel):
    id: int
    name: str
    division: str
    incentive_month: str
    status: str
    row_count: int = 0


class ReportCyclesResponse(BaseModel):
    cycles: List[ReportCycleItem]


class ReportMonthsResponse(BaseModel):
    months: List[str]


class SendReportEmailRequest(BaseModel):
    to_emails: List[str]
    cc_emails: Optional[List[str]] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    file_format: str = "EXCEL"  # "EXCEL" or "CSV"
    division: Optional[str] = None
    hod: Optional[str] = None
    employee: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    selected_rows: Optional[List[dict]] = None


class SendReportEmailResponse(BaseModel):
    success: bool
    message: str
    recipients_sent: List[str]
    filename_attached: str

