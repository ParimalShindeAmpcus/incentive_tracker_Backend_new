from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class CycleCreate(BaseModel):
    name: str
    division: str
    incentive_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    cycle_start_date: Optional[date] = None
    cycle_end_date: Optional[date] = None
    remarks: Optional[str] = None
    candidate_version_id: Optional[int] = None
    recruiter_version_id: Optional[int] = None
    hours_version_id: Optional[int] = None
    project_end_version_id: Optional[int] = None


class CycleUpdate(BaseModel):
    name: Optional[str] = None
    division: Optional[str] = None
    incentive_month: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$")
    cycle_start_date: Optional[date] = None
    cycle_end_date: Optional[date] = None
    remarks: Optional[str] = None
    candidate_version_id: Optional[int] = None
    recruiter_version_id: Optional[int] = None
    hours_version_id: Optional[int] = None
    project_end_version_id: Optional[int] = None


class CycleOut(BaseModel):
    id: int
    name: str
    division: str
    incentive_month: str
    cycle_start_date: Optional[date] = None
    cycle_end_date: Optional[date] = None
    remarks: Optional[str] = None
    status: str
    candidate_version_id: Optional[int] = None
    recruiter_version_id: Optional[int] = None
    hours_version_id: Optional[int] = None
    project_end_version_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CycleSummary(BaseModel):
    cycle_id: int
    status: str
    total_lines: int
    eligible_lines: int
    total_amount: Decimal
    paid_amount: Decimal
    unmatched_matches: int
    blocking_validations: int


class MatchOut(BaseModel):
    id: int
    cycle_id: int
    source_row_ref: Optional[str] = None
    source_candidate_name: Optional[str] = None
    source_candidate_id: Optional[str] = None
    source_client: Optional[str] = None
    hours_worked: Optional[Decimal] = None
    candidate_id: Optional[int] = None
    match_method: Optional[str] = None
    match_result: str
    confidence: Optional[str] = None
    accepted: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class MatchUpdate(BaseModel):
    candidate_id: Optional[int] = None
    match_result: Optional[str] = None
    accepted: Optional[bool] = None
    notes: Optional[str] = None


class ValidationOut(BaseModel):
    id: int
    cycle_id: int
    check_key: str
    severity: str
    message: str
    count: int

    model_config = {"from_attributes": True}


class ChecklistUpdate(BaseModel):
    is_checked: bool
    notes: Optional[str] = None


class ChecklistOut(BaseModel):
    id: int
    cycle_id: int
    item_key: str
    label: Optional[str] = None
    is_checked: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class PaymentStatusOut(BaseModel):
    id: int
    cycle_id: int
    candidate_id: int
    status: str
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class PaymentStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class AdjustmentCreate(BaseModel):
    candidate_id: Optional[int] = None
    candidate_name: Optional[str] = None
    kind: str
    person: Optional[str] = None
    amount: Decimal
    notes: Optional[str] = None


class AdjustmentOut(BaseModel):
    id: int
    cycle_id: int
    candidate_id: Optional[int] = None
    candidate_name: Optional[str] = None
    kind: str
    person: Optional[str] = None
    amount: Decimal
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    comments: Optional[str] = None
    pay: bool = False
