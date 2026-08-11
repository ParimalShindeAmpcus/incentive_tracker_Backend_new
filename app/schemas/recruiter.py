from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class RecruiterStatusOut(BaseModel):
    id: int
    version_id: int
    employee_id: Optional[int] = None
    recruiter_name: str
    status: str
    effective_month: Optional[str] = None

    model_config = {"from_attributes": True}


class RecruiterVersionOut(BaseModel):
    id: int
    version_label: str
    source_filename: Optional[str] = None
    division: Optional[str] = None
    row_count: int
    uploaded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    statuses: List[RecruiterStatusOut] = []

    model_config = {"from_attributes": True}
