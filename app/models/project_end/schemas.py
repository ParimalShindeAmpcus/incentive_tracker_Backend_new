"""Project-end Pydantic DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectEndVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_label: str
    source_filename: Optional[str] = None
    division: Optional[str] = None
    row_count: int
    uploaded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class ProjectEndRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: int
    candidate_id: int
    project_end_date: Optional[date] = None
    project_end: bool
    project_end_source: Optional[str] = None
    hours_before_project_end: Optional[Decimal] = None
    eligibility_flag: Optional[str] = None
    raw_candidate_name: Optional[str] = None
    match_method: Optional[str] = None
    created_at: Optional[datetime] = None


class ProjectEndRecordIn(BaseModel):
    candidate_id: int
    project_end_date: Optional[date] = None
    project_end: bool = True
    project_end_source: Optional[str] = None
    hours_before_project_end: Optional[Decimal] = None
    eligibility_flag: Optional[str] = None
    raw_candidate_name: Optional[str] = None


class CreateProjectEndVersionRequest(BaseModel):
    version_label: str
    division: Optional[str] = None
    source_filename: Optional[str] = None
    notes: Optional[str] = None
    records: List[ProjectEndRecordIn] = Field(default_factory=list)


class ProjectEndVersionDetail(BaseModel):
    version: ProjectEndVersionOut
    records: List[ProjectEndRecordOut]
