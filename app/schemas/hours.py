from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class VersionMetaOut(BaseModel):
    id: int
    version_label: str
    source_filename: Optional[str] = None
    division: Optional[str] = None
    row_count: int
    uploaded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HoursVersionDetail(VersionMetaOut):
    matched_rows: int = 0
    unmatched_rows: int = 0


class ProjectEndVersionDetail(VersionMetaOut):
    matched_rows: int = 0
    unmatched_rows: int = 0


class RecruiterVersionDetail(VersionMetaOut):
    active_count: int = 0
    left_count: int = 0
    notice_count: int = 0


class HoursRowOut(BaseModel):
    id: int
    version_id: int
    candidate_id: int
    work_date: Optional[date] = None
    month_key: Optional[str] = None
    hours_worked: Decimal
    client: Optional[str] = None
    match_method: Optional[str] = None

    model_config = {"from_attributes": True}
