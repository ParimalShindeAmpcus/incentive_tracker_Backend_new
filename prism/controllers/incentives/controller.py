"""Incentive HTTP routes."""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query

from prism.models.incentives.schemas import IncentiveSlabOut
from prism.repositories.entities.user import User
from prism.services.common.deps import DbSession, get_current_user, require_roles
from prism.services.incentives import incentive_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/incentive-slabs", response_model=List[IncentiveSlabOut])
def list_slabs(
    db: DbSession,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    division: Optional[str] = Query(None),
) -> List[IncentiveSlabOut]:
    _ = user
    return incentive_service.list_slabs(db, division=division)
