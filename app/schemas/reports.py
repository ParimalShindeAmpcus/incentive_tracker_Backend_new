from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[int] = None
    details: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportRequest(BaseModel):
    format: str = "xlsx"  # csv | xlsx
