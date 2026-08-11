from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.incentive_slab import IncentiveSlab


def list_active(
    db: Session,
    *,
    division: str,
    as_of: Optional[date] = None,
) -> List[IncentiveSlab]:
    as_of = as_of or date.today()
    q = (
        db.query(IncentiveSlab)
        .filter(
            IncentiveSlab.division == division,
            IncentiveSlab.is_active.is_(True),
            IncentiveSlab.effective_from <= as_of,
        )
    )
    rows = q.all()
    return [r for r in rows if r.effective_to is None or r.effective_to >= as_of]


def find_slab(
    db: Session,
    *,
    division: str,
    slab_type: str,
    role: str,
    margin: Optional[Decimal] = None,
    hours: Optional[Decimal] = None,
    as_of: Optional[date] = None,
) -> Optional[IncentiveSlab]:
    slabs = [
        s
        for s in list_active(db, division=division, as_of=as_of)
        if s.slab_type == slab_type and s.role == role
    ]
    for s in slabs:
        if margin is not None:
            if s.margin_min is not None and margin < s.margin_min:
                continue
            if s.margin_max is not None and margin > s.margin_max:
                continue
        if hours is not None:
            if s.hours_min is not None and hours < s.hours_min:
                continue
            if s.hours_max is not None and hours > s.hours_max:
                continue
        return s
    return None
