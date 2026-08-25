"""Incentive HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.models.incentives.schemas import IncentiveSlabOut
from app.services.common.deps import DbSession
from app.services.incentives import incentive_service

router = APIRouter()


@router.get("/incentive-slabs", response_model=List[IncentiveSlabOut])
def list_slabs(db: DbSession, division: Optional[str] = Query(None)) -> List[IncentiveSlabOut]:
    return incentive_service.list_slabs(db, division=division)
