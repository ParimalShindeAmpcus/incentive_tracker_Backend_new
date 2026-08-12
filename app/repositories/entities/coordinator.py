import enum
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class CoordinatorStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LEFT = "LEFT"
    NOTICE = "NOTICE"

class CoordinatorRecord(Base):
    __tablename__ = "coordinator_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    organization: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    employment_status: Mapped[CoordinatorStatus] = mapped_column(Enum(CoordinatorStatus, name="coordinator_status_enum"), nullable=False, default=CoordinatorStatus.ACTIVE)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    exit_date: Mapped[Optional[date]] = mapped_column(Date)
    bank_name: Mapped[Optional[str]] = mapped_column(String(255))
    account_number: Mapped[Optional[str]] = mapped_column(String(100))
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(50))
    incentive_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
