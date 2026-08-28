"""Incentive repository — SQL only."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.repositories.entities.cycle import CycleStatus, IncentiveCycle
from app.repositories.entities.incentive import IncentiveLine, IncentiveSlab


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


def sn_paid_special_bonuses(db: Session, exclude_cycle_id: int, division: str) -> dict:
    from decimal import Decimal
    import json
    
    rows = (
        db.query(IncentiveLine)
        .join(IncentiveCycle, IncentiveCycle.id == IncentiveLine.cycle_id)
        .filter(
            IncentiveCycle.id != exclude_cycle_id,
            IncentiveCycle.status.in_([CycleStatus.APPROVED, CycleStatus.PAID, CycleStatus.CLOSED]),
            IncentiveCycle.division == division,
            IncentiveLine.incentive_type == "SPECIAL",
            IncentiveLine.role == "Recruiter",
            IncentiveLine.eligible.is_(True),
            IncentiveLine.amount > 0,
        )
        .all()
    )
    
    paid: dict[tuple[str, str], Decimal] = {}
    for r in rows:
        person = (r.person or "").strip().lower()
        start_month = ""
        try:
            if r.explanation:
                meta = json.loads(r.explanation[0])
                start_month = meta.get("start_month", "")
        except Exception:
            pass
            
        if start_month:
            key = (person, start_month)
            paid[key] = paid.get(key, Decimal("0")) + Decimal(str(r.amount or 0))
            
    return paid
