"""Special Incentive HTTP routes."""

from typing import Optional

from fastapi import APIRouter, Query

from app.models.special_incentive.schemas import (
    SpecialIncentiveDetailsResponse,
    SpecialIncentiveResponse,
)
from app.services.common.deps import CurrentUser, DbSession
from app.services.special_incentive import special_incentive_service

router = APIRouter()


@router.get("", response_model=SpecialIncentiveResponse)
def get_special_incentive(
    db: DbSession,
    user: CurrentUser,
    month: str = Query(..., description="Award month as YYYY-MM; filtered via Candidate Master start_date (Start_ID month)"),
) -> SpecialIncentiveResponse:
    """Recruiter of the Month awards from Candidate Master for Ampcus Inc and Bravens Inc."""
    _ = user
    return special_incentive_service.get_special_incentive(db, month)


@router.get(
    "/{organization_key}/{category}/details",
    response_model=SpecialIncentiveDetailsResponse,
)
def get_special_incentive_details(
    organization_key: str,
    category: str,
    db: DbSession,
    user: CurrentUser,
    month: str = Query(..., description="Award month as YYYY-MM"),
    recruiter: Optional[str] = Query(None, description="Optional recruiter filter for details"),
) -> SpecialIncentiveDetailsResponse:
    """Underlying Candidate Master rows used for a Special Incentive award."""
    _ = user
    return special_incentive_service.get_special_incentive_details(
        db,
        month=month,
        organization_key=organization_key,
        category=category,
        recruiter=recruiter,
    )
