"""Incentive repository — SQL only."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.repositories.entities.cycle import CycleStatus, IncentiveCycle
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


def replace_cycle_lines(db: Session, cycle_id: int, rows: List[dict]) -> List[IncentiveLine]:
    db.query(IncentiveLine).filter(IncentiveLine.cycle_id == cycle_id).delete(synchronize_session=False)
    created: List[IncentiveLine] = []
    for data in rows:
        line = IncentiveLine(cycle_id=cycle_id, **data)
        db.add(line)
        created.append(line)
    db.flush()
    return created


def paid_one_time_keys(db: Session, exclude_cycle_id: int) -> set[str]:
    rows = (
        db.query(IncentiveLine)
        .join(IncentiveCycle, IncentiveCycle.id == IncentiveLine.cycle_id)
        .filter(
            IncentiveCycle.id != exclude_cycle_id,
            IncentiveCycle.status.in_([CycleStatus.APPROVED, CycleStatus.PAID, CycleStatus.CLOSED]),
            IncentiveLine.eligible.is_(True),
            IncentiveLine.incentive_type.in_(["ONE_TIME", "SPECIAL", "FULL_TIME", "INHOUSE", "AMPCUS_CLIENT_MARKUP"]),
            IncentiveLine.amount > 0,
        )
        .all()
    )
    keys: set[str] = set()
    for row in rows:
        person = (row.person or "").strip().lower()
        keys.add(f"{row.candidate_id}|{row.incentive_type}|{row.role}|{person}")
    return keys


def list_payments(db: Session, line_id: Optional[int] = None) -> List[IncentivePayment]:
    q = db.query(IncentivePayment)
    if line_id is not None:
        q = q.filter(IncentivePayment.incentive_line_id == line_id)
    return q.order_by(IncentivePayment.id.desc()).all()
