"""Dashboard repository — aggregation queries."""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.repositories.entities.cycle import CycleStatus, IncentiveCycle
from app.repositories.entities.incentive import IncentiveLine
from app.repositories.entities.organization import Division


ACTIVE_STATUSES = {
    CycleStatus.DRAFT,
    CycleStatus.MATCHED,
    CycleStatus.VALIDATED,
    CycleStatus.CALCULATED,
}

DRAFT_LIKE = {
    CycleStatus.DRAFT,
    CycleStatus.MATCHED,
    CycleStatus.VALIDATED,
}


def list_active_divisions(db: Session) -> List[Division]:
    return (
        db.query(Division)
        .filter(Division.is_active.is_(True))
        .order_by(Division.id.asc())
        .all()
    )


def list_cycles_filtered(
    db: Session,
    *,
    division: Optional[str] = None,
    year: Optional[str] = None,
    month: Optional[str] = None,
) -> List[IncentiveCycle]:
    q = db.query(IncentiveCycle)
    if division:
        q = q.filter(IncentiveCycle.division == division)
    if year and year != "ALL":
        q = q.filter(IncentiveCycle.incentive_month.like(f"{year}-%"))
    if month and month != "ALL":
        # month is MM
        q = q.filter(IncentiveCycle.incentive_month.like(f"%-{month}"))
    return q.order_by(IncentiveCycle.id.desc()).all()


def list_all_cycles_for_division_cards(db: Session) -> List[IncentiveCycle]:
    """Unfiltered cycles used to build per-division card stats."""
    return db.query(IncentiveCycle).order_by(IncentiveCycle.id.desc()).all()


def incentive_totals_by_cycle(db: Session, cycle_ids: List[int]) -> Dict[int, Decimal]:
    if not cycle_ids:
        return {}
    rows: List[Tuple[int, Decimal]] = (
        db.query(
            IncentiveLine.cycle_id,
            func.coalesce(func.sum(IncentiveLine.amount), 0),
        )
        .filter(
            IncentiveLine.cycle_id.in_(cycle_ids),
            IncentiveLine.eligible.is_(True),
        )
        .group_by(IncentiveLine.cycle_id)
        .all()
    )
    return {cid: Decimal(str(total or 0)) for cid, total in rows}
