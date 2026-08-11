"""Incentive repository — SQL only."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.repositories.entities.incentive import IncentiveLine, IncentivePayment, IncentiveSlab


def list_lines(db: Session, cycle_id: int) -> List[IncentiveLine]:
    return (
        db.query(IncentiveLine)
        .filter(IncentiveLine.cycle_id == cycle_id)
        .order_by(IncentiveLine.id)
        .all()
    )


def get_line(db: Session, line_id: int) -> Optional[IncentiveLine]:
    return db.query(IncentiveLine).filter(IncentiveLine.id == line_id).first()


def list_slabs(db: Session, division: Optional[str] = None) -> List[IncentiveSlab]:
    q = db.query(IncentiveSlab).filter(IncentiveSlab.is_active.is_(True))
    if division:
        q = q.filter(IncentiveSlab.division == division)
    return q.order_by(IncentiveSlab.division, IncentiveSlab.role, IncentiveSlab.slab_type).all()


def create_slab(db: Session, data: dict) -> IncentiveSlab:
    row = IncentiveSlab(**data)
    db.add(row)
    db.flush()
    return row


def create_payment(db: Session, data: dict) -> IncentivePayment:
    row = IncentivePayment(**data)
    db.add(row)
    db.flush()
    return row


def list_payments(db: Session, line_id: Optional[int] = None) -> List[IncentivePayment]:
    q = db.query(IncentivePayment)
    if line_id is not None:
        q = q.filter(IncentivePayment.incentive_line_id == line_id)
    return q.order_by(IncentivePayment.id.desc()).all()
