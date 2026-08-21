"""VLOOKUP reconciliation ORM entities (template + client hours matching)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base


class VLookupTemplateCandidate(Base):
    """Hours Template rows used as the matching pool for a batch."""

    __tablename__ = "vlookup_template_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    client_name: Mapped[Optional[str]] = mapped_column(String(255))
    template_hours: Mapped[int] = mapped_column(Integer, default=0)
    month: Mapped[Optional[str]] = mapped_column(String(20))

    contract_type: Mapped[Optional[str]] = mapped_column(String(20))
    division: Mapped[Optional[str]] = mapped_column(String(50))
    recruiter_name: Mapped[Optional[str]] = mapped_column(String(255))

    upload_batch_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VLookupWeeklyHours(Base):
    """Parsed weekly/client hours rows from the messy client file."""

    __tablename__ = "vlookup_weekly_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_name_messy: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hours_worked: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[Optional[str]] = mapped_column(String(20))
    month: Mapped[Optional[str]] = mapped_column(String(20))
    client_name: Mapped[Optional[str]] = mapped_column(String(255))
    normalized_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    upload_batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VLookupMatchedRecord(Base):
    """One reconciliation result per client candidate-month group."""

    __tablename__ = "vlookup_matched_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    template_candidate_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    template_candidate_name: Mapped[Optional[str]] = mapped_column(String(255))
    template_candidate_id_str: Mapped[Optional[str]] = mapped_column(String(50))

    messy_name_original: Mapped[Optional[str]] = mapped_column(String(255))
    messy_client_name: Mapped[Optional[str]] = mapped_column(String(255))
    messy_month: Mapped[Optional[str]] = mapped_column(String(20))
    weekly_breakdown: Mapped[Optional[Any]] = mapped_column(JSON)
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    match_method: Mapped[Optional[str]] = mapped_column(String(50))
    match_explanation: Mapped[Optional[Any]] = mapped_column(JSON)

    manually_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255))
    review_action: Mapped[Optional[str]] = mapped_column(String(20))
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    upload_batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VLookupUploadBatch(Base):
    """Upload batch metadata and reconciliation stats."""

    __tablename__ = "vlookup_upload_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(40))
    filename: Mapped[Optional[str]] = mapped_column(String(255))
    total_records: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[Optional[str]] = mapped_column(String(20))

    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0)
    unmatched_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    conflicting_count: Mapped[int] = mapped_column(Integer, default=0)

    target_month: Mapped[Optional[str]] = mapped_column(String(20))
    client_file_format: Mapped[Optional[str]] = mapped_column(String(50))
    parser_warnings: Mapped[Optional[Any]] = mapped_column(JSON)

    uploaded_by: Mapped[Optional[str]] = mapped_column(String(255))
    cancelled_by: Mapped[Optional[str]] = mapped_column(String(255))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    stage: Mapped[Optional[str]] = mapped_column(String(40))
    cycle_id: Mapped[Optional[int]] = mapped_column(Integer)
    resume_state: Mapped[Optional[Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
