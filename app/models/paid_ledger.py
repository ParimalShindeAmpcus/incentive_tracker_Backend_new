from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PaidIncentiveLedger(Base):
    __tablename__ = "paid_incentive_ledger"
    __table_args__ = (
        UniqueConstraint(
            "dedupe_key",
            name="uq_paid_ledger_dedupe_key",
        ),
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

    payment = relationship("IncentivePayment", back_populates="ledger_entries")
