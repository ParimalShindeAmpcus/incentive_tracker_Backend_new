import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditAction(str, enum.Enum):
    LOGIN = "LOGIN"
    UPLOAD = "UPLOAD"
    IMPORT = "IMPORT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    MATCH = "MATCH"
    VALIDATION = "VALIDATION"
    CALCULATION = "CALCULATION"
    ADJUSTMENT = "ADJUSTMENT"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"
    PAYMENT = "PAYMENT"
    EXPORT = "EXPORT"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action_enum"), nullable=False, index=True
    )
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    details: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
