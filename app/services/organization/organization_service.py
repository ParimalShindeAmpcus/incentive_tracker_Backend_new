"""Organization service."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.organization.schemas import DivisionOut, EmployeeOut, OrganizationOut
from app.repositories.organization import organization_repository


def list_organizations(db: Session) -> List[OrganizationOut]:
    rows = organization_repository.list_organizations(db)
    return [OrganizationOut.model_validate(r) for r in rows]


def list_divisions(db: Session, organization_id: Optional[int] = None) -> List[DivisionOut]:
    rows = organization_repository.list_divisions(db, organization_id=organization_id)
    return [DivisionOut.model_validate(r) for r in rows]


def list_employees(db: Session, division_id: Optional[int] = None) -> List[EmployeeOut]:
    rows = organization_repository.list_employees(db, division_id=division_id)
    return [EmployeeOut.model_validate(r) for r in rows]
