"""Recruiter Pydantic DTOs."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class RecruiterStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: int
    employee_id: Optional[int] = None
    recruiter_name: str
    normalized_name: str
    email: Optional[str] = None
    organization: Optional[str] = None
    role: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    status: str
    effective_month: Optional[str] = None
    effective_from: Optional[date] = None
    exit_date: Optional[date] = None
    incentive_active: bool
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_serializer("status")
    def serialize_status(self, v):
        return v.value if hasattr(v, "value") else v


class RecruiterVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_label: str
    source_filename: Optional[str] = None
    division: Optional[str] = None
    row_count: int
    uploaded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class RecruiterStatusIn(BaseModel):
    recruiter_name: str
    email: Optional[str] = None
    organization: Optional[str] = None
    role: Optional[str] = None
    status: str = "ACTIVE"
    effective_month: Optional[str] = None
    employee_id: Optional[int] = None
    incentive_active: bool = True
    notes: Optional[str] = None


class CreateRecruiterVersionRequest(BaseModel):
    version_label: str
    division: Optional[str] = None
    source_filename: Optional[str] = None
    notes: Optional[str] = None
    statuses: List[RecruiterStatusIn] = Field(default_factory=list)


class RecruiterVersionCreateResponse(BaseModel):
    version: RecruiterVersionOut
    created_count: int
