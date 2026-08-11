from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
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


class IncentiveLine(Base):
    __tablename__ = "incentive_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("incentive_cycles.id"), nullable=False, index=True)
    candidate_id: Mapped[Optional[int]] = mapped_column(ForeignKey("candidates.id"), index=True)
    candidate_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    person: Mapped[str] = mapped_column(String(255), nullable=False)
    incentive_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_applied: Mapped[Optional[str]] = mapped_column(String(255))
    eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    base_incentive: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    pro_rata_factor: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=1)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    explanation_json: Mapped[Optional[str]] = mapped_column(Text)
    payment_status: Mapped[str] = mapped_column(String(50), default="UNPAID", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cycle = relationship("IncentiveCycle", back_populates="lines", foreign_keys=[cycle_id])
    approvals: Mapped[List["IncentiveApproval"]] = relationship(
        "IncentiveApproval", back_populates="line", cascade="all, delete-orphan"
    )
    payments: Mapped[List["IncentivePayment"]] = relationship(
        "IncentivePayment", back_populates="line", cascade="all, delete-orphan"
    )


class IncentiveApproval(Base):
    __tablename__ = "incentive_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incentive_line_id: Mapped[int] = mapped_column(
        ForeignKey("incentive_lines.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # APPROVE / REJECT
    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    comments: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    line: Mapped[IncentiveLine] = relationship("IncentiveLine", back_populates="approvals")


class IncentivePayment(Base):
    __tablename__ = "incentive_payments"
    __table_args__ = (
        UniqueConstraint("incentive_line_id", name="uq_incentive_payment_line"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incentive_line_id: Mapped[int] = mapped_column(
        ForeignKey("incentive_lines.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100))
    paid_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="PAID", nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[Optional[str]] = mapped_column(Text)

    line: Mapped[IncentiveLine] = relationship("IncentiveLine", back_populates="payments")
    ledger_entries: Mapped[List["PaidIncentiveLedger"]] = relationship(
        "PaidIncentiveLedger",
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class PaidIncentiveLedger(Base):
    __tablename__ = "paid_incentive_ledger"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_paid_ledger_dedupe_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("incentive_payments.id"), nullable=False, index=True
    )
    cycle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incentive_cycles.id"))
    candidate_id: Mapped[Optional[int]] = mapped_column(ForeignKey("candidates.id"))
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    person: Mapped[str] = mapped_column(String(255), nullable=False)
    incentive_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    payment: Mapped[IncentivePayment] = relationship(
        "IncentivePayment", back_populates="ledger_entries"
    )


class IncentiveSlab(Base):
    __tablename__ = "incentive_slabs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    division: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    slab_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    margin_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    margin_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    hours_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    hours_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
