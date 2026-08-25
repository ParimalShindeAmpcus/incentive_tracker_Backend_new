from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
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
