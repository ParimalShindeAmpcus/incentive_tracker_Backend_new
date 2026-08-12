"""Audit Pydantic DTOs — aligned with frontend AuditLogItem contract."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.repositories.entities.audit import AuditAction


class AuditLogCreate(BaseModel):
    action: AuditAction
    title: str
    details: str
    user: Optional[str] = None
    username: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime
    action: AuditAction
    title: str
    details: str
    user: str
    username: str
    metadata: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata_json")

    @field_serializer("action")
    def serialize_action(self, v: AuditAction) -> str:
        return v.value if hasattr(v, "value") else str(v)

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: Optional[datetime]) -> Optional[str]:
        return v.isoformat() if v is not None else None

    @classmethod
    def from_orm_row(cls, row) -> "AuditLogOut":
        return cls(
            id=f"LOG-{row.id}",
            timestamp=row.created_at,
            action=row.action,
            title=row.title,
            details=row.details or "",
            user=row.user_display or "",
            username=row.username or "",
            metadata=row.metadata_json,
        )
