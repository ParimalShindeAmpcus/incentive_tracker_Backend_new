"""Hours Pydantic DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VersionMetaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_label: str
    source_filename: Optional[str] = None
    division: Optional[str] = None
    row_count: int
    uploaded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class HoursRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: int
    candidate_id: int
    external_candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
    work_date: Optional[date] = None
    month_key: Optional[str] = None
    hours_worked: Decimal
    client: Optional[str] = None
    source_row: Optional[int] = None
    raw_candidate_name: Optional[str] = None
    match_method: Optional[str] = None
    match_confidence: Optional[str] = None
    created_at: Optional[datetime] = None


class HoursVersionDetail(BaseModel):
    version: VersionMetaOut
    rows: List[HoursRowOut]


class HoursRowIn(BaseModel):
    """Accept either DB candidate_id or Excel external_candidate_id (Candidate ID column)."""

    candidate_id: Optional[int] = None
    external_candidate_id: Optional[str] = None
    hours_worked: Decimal
    work_date: Optional[date] = None
    month_key: Optional[str] = None
    client: Optional[str] = None
    raw_candidate_name: Optional[str] = None
    source_row: Optional[int] = None

    @model_validator(mode="after")
    def require_candidate_ref(self) -> "HoursRowIn":
        external = (self.external_candidate_id or "").strip()
        if self.candidate_id is None and not external:
            raise ValueError("Either candidate_id or external_candidate_id is required")
        if external:
            self.external_candidate_id = external
        return self


class CreateHoursVersionRequest(BaseModel):
    version_label: str
    division: Optional[str] = None
    source_filename: Optional[str] = None
    notes: Optional[str] = None
    rows: List[HoursRowIn] = Field(default_factory=list)


class HoursBenchmarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    division: str
    benchmark_hours: Decimal
    description: Optional[str] = None
    is_active: bool
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HoursBenchmarkUpdate(BaseModel):
    benchmark_hours: Decimal
    description: Optional[str] = None
    is_active: Optional[bool] = None


class HoursRowHoursUpdate(BaseModel):
    hours_worked: Decimal
