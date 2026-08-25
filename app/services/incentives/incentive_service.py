"""Incentive service."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.incentives.schemas import IncentiveSlabOut
from app.repositories.incentives import incentive_repository


def list_slabs(db: Session, division: Optional[str] = None) -> List[IncentiveSlabOut]:
    rows = incentive_repository.list_slabs(db, division=division)
    return [IncentiveSlabOut.model_validate(r) for r in rows]
