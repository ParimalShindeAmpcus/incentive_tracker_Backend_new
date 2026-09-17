"""Organization HTTP routes — authenticated ADMIN/ACCOUNTS reference data."""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query

from app.models.organization.schemas import DivisionOut, OrganizationOut
from app.repositories.entities.user import User
from app.services.common.deps import DbSession, get_current_user, require_roles
from app.services.organization import organization_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/organizations", response_model=List[OrganizationOut])
def get_organizations(
    db: DbSession,
    user: Annotated[User, Depends(require_roles("ADMIN", "ACCOUNTS"))],
) -> List[OrganizationOut]:
    _ = user
    return organization_service.list_organizations(db)


@router.get("/divisions", response_model=List[DivisionOut])
def get_divisions(
    db: DbSession,
    user: Annotated[User, Depends(require_roles("ADMIN", "ACCOUNTS"))],
    organization_id: Optional[int] = Query(
        None,
        description="Optional organization filter; must exist and be active when set",
    ),
) -> List[DivisionOut]:
    _ = user
    return organization_service.list_divisions(db, organization_id=organization_id)
