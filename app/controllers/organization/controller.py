"""Organization HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.models.organization.schemas import DivisionOut, OrganizationOut
from app.services.common.deps import DbSession, get_current_user
from app.services.organization import organization_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/organizations", response_model=List[OrganizationOut])
def get_organizations(db: DbSession) -> List[OrganizationOut]:
    return organization_service.list_organizations(db)


@router.get("/divisions", response_model=List[DivisionOut])
def get_divisions(
    db: DbSession,
    organization_id: Optional[int] = Query(None),
) -> List[DivisionOut]:
    return organization_service.list_divisions(db, organization_id=organization_id)
