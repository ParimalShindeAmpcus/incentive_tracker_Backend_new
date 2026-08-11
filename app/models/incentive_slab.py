from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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
