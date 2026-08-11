"""Incentive HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.models.incentives.schemas import IncentiveSlabOut, PaymentCreate, PaymentOut
from app.services.common.deps import CurrentUser, DbSession
from app.services.incentives import incentive_service

router = APIRouter()


@router.get("/incentive-slabs", response_model=List[IncentiveSlabOut])
def list_slabs(db: DbSession, division: Optional[str] = Query(None)) -> List[IncentiveSlabOut]:
    return incentive_service.list_slabs(db, division=division)


@router.post("/payments", response_model=PaymentOut)
def create_payment(payload: PaymentCreate, db: DbSession, user: CurrentUser) -> PaymentOut:
    return incentive_service.create_payment(db, payload, paid_by=user.id)
