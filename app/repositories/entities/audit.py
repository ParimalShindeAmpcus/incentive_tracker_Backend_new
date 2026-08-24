import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditAction(str, enum.Enum):
    FILE_UPLOAD = "FILE_UPLOAD"
    FILE_DOWNLOAD = "FILE_DOWNLOAD"
    CANDIDATE_ADD = "CANDIDATE_ADD"
    CANDIDATE_TOGGLE = "CANDIDATE_TOGGLE"
    CANDIDATE_UPDATE = "CANDIDATE_UPDATE"
    COORDINATOR_TOGGLE = "COORDINATOR_TOGGLE"
    COORDINATOR_ADD = "COORDINATOR_ADD"
    COORDINATOR_DELETE = "COORDINATOR_DELETE"
    HOURS_RECONCILIATION = "HOURS_RECONCILIATION"
    CALCULATION_RUN = "CALCULATION_RUN"
    CYCLE_APPROVE = "CYCLE_APPROVE"
    CYCLE_CANCEL = "CYCLE_CANCEL"
    PAYMENT_UPDATE = "PAYMENT_UPDATE"
    REPORT_EXPORT = "REPORT_EXPORT"
    VLOOKUP_MATCH_COMPLETED = "VLOOKUP_MATCH_COMPLETED"
    VLOOKUP_MATCH_CANCELLED = "VLOOKUP_MATCH_CANCELLED"
    VLOOKUP_DRAFT_RESUMED = "VLOOKUP_DRAFT_RESUMED"
    SYSTEM = "SYSTEM"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action_enum", native_enum=False, length=50),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    details: Mapped[Optional[str]] = mapped_column(Text)
    user_display: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    username: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
