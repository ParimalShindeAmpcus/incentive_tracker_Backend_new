from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.repositories import incentive_slab_repo


def list_slabs(db: Session, division: str):
    return incentive_slab_repo.list_active(db, division=division)


def lookup_amount(
    db: Session,
    *,
    division: str,
    slab_type: str,
    role: str,
    margin: Optional[Decimal] = None,
    hours: Optional[Decimal] = None,
) -> Optional[Decimal]:
    slab = incentive_slab_repo.find_slab(
        db,
        division=division,
        slab_type=slab_type,
        role=role,
        margin=margin,
        hours=hours,
    )
    return slab.amount if slab else None
