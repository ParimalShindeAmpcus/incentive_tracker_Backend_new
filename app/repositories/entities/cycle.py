import enum
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.repositories.entities.incentive import IncentiveLine


class CycleStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    MATCHED = "MATCHED"
    VALIDATED = "VALIDATED"
    CALCULATED = "CALCULATED"
    APPROVED = "APPROVED"
    PAID = "PAID"
    CLOSED = "CLOSED"


class MatchResult(str, enum.Enum):
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    DUPLICATE = "DUPLICATE"
    MANUAL = "MANUAL"
    REJECTED = "REJECTED"


class IncentiveCycle(Base):
    __tablename__ = "incentive_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    division: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    incentive_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # YYYY-MM
    cycle_start_date: Mapped[Optional[date]] = mapped_column(Date)
    cycle_end_date: Mapped[Optional[date]] = mapped_column(Date)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[CycleStatus] = mapped_column(
        Enum(CycleStatus, name="cycle_status_enum"),
        default=CycleStatus.DRAFT,
        nullable=False,
    )
    candidate_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("candidate_data_versions.id")
    )
    recruiter_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("recruiter_master_versions.id")
    )
    hours_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hours_data_versions.id"))
    project_end_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project_end_versions.id")
    )
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    snapshots: Mapped[List["CycleDataSnapshot"]] = relationship(
        "CycleDataSnapshot", back_populates="cycle", cascade="all, delete-orphan"
    )
    matches: Mapped[List["CycleHoursMatch"]] = relationship(
        "CycleHoursMatch", back_populates="cycle", cascade="all, delete-orphan"
    )
    validations: Mapped[List["CycleValidationResult"]] = relationship(
        "CycleValidationResult", back_populates="cycle", cascade="all, delete-orphan"
    )
    checklist_items: Mapped[List["CycleChecklistItem"]] = relationship(
        "CycleChecklistItem", back_populates="cycle", cascade="all, delete-orphan"
    )
    payment_statuses: Mapped[List["CyclePaymentStatus"]] = relationship(
        "CyclePaymentStatus", back_populates="cycle", cascade="all, delete-orphan"
    )
    adjustments: Mapped[List["CycleManualAdjustment"]] = relationship(
        "CycleManualAdjustment", back_populates="cycle", cascade="all, delete-orphan"
    )
    lines: Mapped[List["IncentiveLine"]] = relationship(
        "IncentiveLine",
        back_populates="cycle",
        cascade="all, delete-orphan",
        foreign_keys="IncentiveLine.cycle_id",
    )


class CycleDataSnapshot(Base):
    __tablename__ = "cycle_data_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("incentive_cycles.id"), nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cycle: Mapped[IncentiveCycle] = relationship("IncentiveCycle", back_populates="snapshots")


class CycleHoursMatch(Base):
    __tablename__ = "cycle_hours_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("incentive_cycles.id"), nullable=False, index=True)
    source_row_ref: Mapped[Optional[str]] = mapped_column(String(100))
    source_candidate_name: Mapped[Optional[str]] = mapped_column(String(255))
    source_candidate_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_client: Mapped[Optional[str]] = mapped_column(String(255))
    hours_worked: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    candidate_id: Mapped[Optional[int]] = mapped_column(ForeignKey("candidates.id"))
    match_method: Mapped[Optional[str]] = mapped_column(String(50))
    match_result: Mapped[MatchResult] = mapped_column(
        Enum(MatchResult, name="match_result_enum"),
        default=MatchResult.UNMATCHED,
        nullable=False,
    )
    confidence: Mapped[Optional[str]] = mapped_column(String(50))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cycle: Mapped[IncentiveCycle] = relationship("IncentiveCycle", back_populates="matches")


class CycleValidationResult(Base):
    __tablename__ = "cycle_validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("incentive_cycles.id"), nullable=False, index=True)
    check_key: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # GREEN/YELLOW/RED
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cycle: Mapped[IncentiveCycle] = relationship("IncentiveCycle", back_populates="validations")


class CycleChecklistItem(Base):
    __tablename__ = "cycle_checklist_items"
    __table_args__ = (UniqueConstraint("cycle_id", "item_key", name="uq_cycle_checklist_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("incentive_cycles.id"), nullable=False, index=True)
    item_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255))
    is_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    cycle: Mapped[IncentiveCycle] = relationship("IncentiveCycle", back_populates="checklist_items")


class CyclePaymentStatus(Base):
    __tablename__ = "cycle_payment_statuses"
    __table_args__ = (
        UniqueConstraint("cycle_id", "candidate_id", name="uq_cycle_payment_candidate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("incentive_cycles.id"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    payment_received_date: Mapped[Optional[date]] = mapped_column(Date)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cycle: Mapped[IncentiveCycle] = relationship("IncentiveCycle", back_populates="payment_statuses")


class CycleManualAdjustment(Base):
    __tablename__ = "cycle_manual_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("incentive_cycles.id"), nullable=False, index=True)
    candidate_id: Mapped[Optional[int]] = mapped_column(ForeignKey("candidates.id"))
    candidate_name: Mapped[Optional[str]] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    person: Mapped[Optional[str]] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cycle: Mapped[IncentiveCycle] = relationship("IncentiveCycle", back_populates="adjustments")
