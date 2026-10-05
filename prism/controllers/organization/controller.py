from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, Path

from prism.models.organization.schemas import (
    DivisionCreate,
    DivisionOut,
    DivisionUpdate,
    OrganizationOut,
)
from prism.repositories.entities.user import User
from prism.services.common.deps import DbSession, get_current_user, require_roles
from prism.services.organization import organization_service

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
    active_only: bool = Query(
        False,
        description="Filter for active divisions only or return all",
    ),
) -> List[DivisionOut]:
    _ = user
    return organization_service.list_divisions(
        db, organization_id=organization_id, active_only=active_only
    )


@router.get("/divisions/{division_id}", response_model=DivisionOut)
def get_division_by_id(
    division_id: int,
    db: DbSession,
    user: Annotated[User, Depends(require_roles("ADMIN", "ACCOUNTS"))],
) -> DivisionOut:
    _ = user
    return organization_service.get_division(db, division_id)


@router.post("/divisions", response_model=DivisionOut)
def create_division(
    payload: DivisionCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
) -> DivisionOut:
    return organization_service.create_division(db, payload, user_id=user.id)


@router.put("/divisions/{division_id}", response_model=DivisionOut)
def update_division(
    division_id: int,
    payload: DivisionUpdate,
    db: DbSession,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
) -> DivisionOut:
    return organization_service.update_division(db, division_id, payload, user_id=user.id)


@router.patch("/divisions/{division_id}/toggle", response_model=DivisionOut)
def toggle_division(
    division_id: int,
    db: DbSession,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
) -> DivisionOut:
    return organization_service.toggle_division(db, division_id, user_id=user.id)


@router.delete("/divisions/{division_id}", response_model=DivisionOut)
def delete_division(
    division_id: int,
    db: DbSession,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
) -> DivisionOut:
    return organization_service.delete_division(db, division_id, user_id=user.id)

