import enum
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RecruiterStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LEFT = "LEFT"
    NOTICE = "NOTICE"


class RecruiterMasterVersion(Base):
    __tablename__ = "recruiter_master_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255))
    division: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    statuses: Mapped[List["RecruiterStatus"]] = relationship(
        "RecruiterStatus", back_populates="version"
    )


class RecruiterStatus(Base):
    __tablename__ = "recruiter_statuses"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "employee_id", "effective_month", name="uq_recruiter_status_version_emp_month"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("recruiter_master_versions.id"), nullable=False, index=True
    )
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"))
    recruiter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[RecruiterStatusEnum] = mapped_column(
        Enum(RecruiterStatusEnum, name="recruiter_status_enum"),
        nullable=False,
        default=RecruiterStatusEnum.ACTIVE,
    )
    effective_month: Mapped[Optional[str]] = mapped_column(String(7))  # YYYY-MM
    effective_from: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    version: Mapped[RecruiterMasterVersion] = relationship(
        "RecruiterMasterVersion", back_populates="statuses"
    )
