"""Incentive service."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.incentives.schemas import IncentiveSlabOut, PaymentCreate, PaymentOut
from app.repositories.incentives import incentive_repository


def list_slabs(db: Session, division: Optional[str] = None) -> List[IncentiveSlabOut]:
    rows = incentive_repository.list_slabs(db, division=division)
    return [IncentiveSlabOut.model_validate(r) for r in rows]


def create_payment(db: Session, payload: PaymentCreate, paid_by: Optional[int] = None) -> PaymentOut:
    line = incentive_repository.get_line(db, payload.incentive_line_id)
    if line is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incentive line not found")
    data = payload.model_dump()
    data["paid_by"] = paid_by
    payment = incentive_repository.create_payment(db, data)
    line.payment_status = payload.status
    db.add(line)
    db.commit()
    db.refresh(payment)
    return PaymentOut.model_validate(payment)
