"""Cycle Pydantic DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.incentives.schemas import IncentiveLineOut


class CycleCreate(BaseModel):
    name: str
    division: str
    incentive_month: str
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
    incentive_month: Optional[str] = None
    cycle_start_date: Optional[date] = None
    cycle_end_date: Optional[date] = None
    remarks: Optional[str] = None
    status: Optional[str] = None
    candidate_version_id: Optional[int] = None
    recruiter_version_id: Optional[int] = None
    hours_version_id: Optional[int] = None
    project_end_version_id: Optional[int] = None


class CycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    approved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_serializer("status")
    def serialize_status(self, v):
        return v.value if hasattr(v, "value") else v


class CycleSummary(BaseModel):
    cycle_id: int
    status: str
    match_count: int = 0
    validation_count: int = 0
    checklist_checked: int = 0
    checklist_total: int = 0
    line_count: int = 0
    total_amount: Decimal = Decimal("0")


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @field_serializer("match_result")
    def serialize_match_result(self, v):
        return v.value if hasattr(v, "value") else v


class MatchUpdate(BaseModel):
    candidate_id: Optional[int] = None
    match_result: Optional[str] = None
    accepted: Optional[bool] = None
    notes: Optional[str] = None
    match_method: Optional[str] = None


class ValidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cycle_id: int
    check_key: str
    severity: str
    message: str
    count: int
    details_json: Optional[str] = None
    created_at: Optional[datetime] = None


class ChecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cycle_id: int
    item_key: str
    label: Optional[str] = None
    is_checked: bool
    checked_by: Optional[int] = None
    checked_at: Optional[datetime] = None
    notes: Optional[str] = None


class ChecklistUpdate(BaseModel):
    is_checked: bool
    notes: Optional[str] = None


class PaymentStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cycle_id: int
    candidate_id: int
    status: str
    notes: Optional[str] = None
    updated_by: Optional[int] = None
    updated_at: Optional[datetime] = None


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    cycle_id: int
    candidate_id: Optional[int] = None
    candidate_name: Optional[str] = None
    kind: str
    person: Optional[str] = None
    amount: Decimal
    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


class ApproveRequest(BaseModel):
    comments: Optional[str] = None


class CalculateRequest(BaseModel):
    force: bool = False


class MatchStatsOut(BaseModel):
    total_hours_rows: int = 0
    matched_name_and_id: int = 0
    matched_id_fallback: int = 0
    name_id_mismatch: int = 0
    unmatched: int = 0
    inactive: int = 0
    already_paid: int = 0


class CalculateResult(BaseModel):
    cycle: CycleOut
    stats: MatchStatsOut
    line_count: int
    eligible_line_count: int
    total_amount: Decimal
    lines: List[IncentiveLineOut]
    validations: List[ValidationOut]


class HoursUploadOut(BaseModel):
    cycle_id: int
    row_count: int
    message: str
