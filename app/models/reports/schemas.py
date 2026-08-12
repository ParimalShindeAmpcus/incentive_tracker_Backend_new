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


class ReportResponse(BaseModel):
    rows: List[ReportRowOut]
    total_rows: int
    total_incentive: Decimal


class ReportTeamsResponse(BaseModel):
    teams: List[str]
