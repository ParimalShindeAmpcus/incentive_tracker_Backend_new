from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class HoursDataVersion(Base):
    __tablename__ = "hours_data_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255))
    division: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rows: Mapped[List["HoursRow"]] = relationship("HoursRow", back_populates="version")


class HoursRow(Base):
    __tablename__ = "hours_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("hours_data_versions.id"), nullable=False, index=True
    )
    # Hard rule: must reference an existing candidate; never creates one
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    work_date: Mapped[Optional[date]] = mapped_column(Date)
    month_key: Mapped[Optional[str]] = mapped_column(String(7), index=True)
    hours_worked: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    client: Mapped[Optional[str]] = mapped_column(String(255))
    source_row: Mapped[Optional[int]] = mapped_column(Integer)
    raw_candidate_name: Mapped[Optional[str]] = mapped_column(String(255))
    match_method: Mapped[Optional[str]] = mapped_column(String(50))
    match_confidence: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    version: Mapped[HoursDataVersion] = relationship("HoursDataVersion", back_populates="rows")


class HoursBenchmark(Base):
    __tablename__ = "hours_benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    division: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    benchmark_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
