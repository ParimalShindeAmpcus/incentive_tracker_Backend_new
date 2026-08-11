from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ProjectEndVersion(Base):
    __tablename__ = "project_end_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255))
    division: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    records: Mapped[List["ProjectEndRecord"]] = relationship(
        "ProjectEndRecord", back_populates="version"
    )


class ProjectEndRecord(Base):
    __tablename__ = "project_end_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("project_end_versions.id"), nullable=False, index=True
    )
    # Hard rule: non-nullable FK to candidates — never creates candidates
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    project_end_date: Mapped[Optional[date]] = mapped_column(Date)
    project_end: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    project_end_source: Mapped[Optional[str]] = mapped_column(String(100))
    hours_before_project_end: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    eligibility_flag: Mapped[Optional[str]] = mapped_column(String(100))
    raw_candidate_name: Mapped[Optional[str]] = mapped_column(String(255))
    match_method: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    version: Mapped[ProjectEndVersion] = relationship("ProjectEndVersion", back_populates="records")
