"""Audit Pydantic DTOs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_serializer


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[int] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_serializer("action")
    def serialize_action(self, v):
        return v.value if hasattr(v, "value") else v
