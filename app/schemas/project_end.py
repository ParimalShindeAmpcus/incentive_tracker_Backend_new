from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ProjectEndRecordOut(BaseModel):
    id: int
    version_id: int
    candidate_id: int
    project_end_date: Optional[date] = None
    project_end: bool
    project_end_source: Optional[str] = None
    hours_before_project_end: Optional[Decimal] = None
    eligibility_flag: Optional[str] = None
    match_method: Optional[str] = None

    model_config = {"from_attributes": True}


class ProjectEndVersionOut(BaseModel):
    id: int
    version_label: str
    source_filename: Optional[str] = None
    division: Optional[str] = None
    row_count: int
    uploaded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
