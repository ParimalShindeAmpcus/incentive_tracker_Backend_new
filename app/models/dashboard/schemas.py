"""Dashboard Pydantic DTOs."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class DashboardMetrics(BaseModel):
    cycles_run: int = 0
    in_draft: int = 0
    calculated: int = 0
    approved_incentive: Decimal = Decimal("0")


class DivisionCardOut(BaseModel):
    code: str
    name: str
    approved: int = 0
    active: int = 0
    cancelled: int = 0
    latest_month: Optional[str] = None
    latest_label: Optional[str] = None
    next_label: str = "—"


class DashboardCycleRow(BaseModel):
    id: int
    name: str
    division: str
    incentive_month: str
    status: str
    total_incentive: Decimal = Decimal("0")
    cycle_start_date: Optional[str] = None
    cycle_end_date: Optional[str] = None
    created_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None


class DashboardResponse(BaseModel):
    metrics: DashboardMetrics
    divisions: List[DivisionCardOut] = Field(default_factory=list)
    recent_cycles: List[DashboardCycleRow] = Field(default_factory=list)
