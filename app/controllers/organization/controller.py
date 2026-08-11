"""Organization HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.models.organization.schemas import DivisionOut, EmployeeOut, OrganizationOut
from app.services.common.deps import DbSession
from app.services.organization import organization_service

router = APIRouter()


@router.get("/organizations", response_model=List[OrganizationOut])
def get_organizations(db: DbSession) -> List[OrganizationOut]:
    return organization_service.list_organizations(db)


@router.get("/divisions", response_model=List[DivisionOut])
def get_divisions(
    db: DbSession,
    organization_id: Optional[int] = Query(None),
) -> List[DivisionOut]:
    return organization_service.list_divisions(db, organization_id=organization_id)


@router.get("/employees", response_model=List[EmployeeOut])
def get_employees(
    db: DbSession,
    division_id: Optional[int] = Query(None),
) -> List[EmployeeOut]:
    return organization_service.list_employees(db, division_id=division_id)
