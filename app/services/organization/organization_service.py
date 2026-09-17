"""Organization service."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.organization.schemas import DivisionOut, OrganizationOut
from app.repositories.organization import organization_repository


def list_organizations(db: Session) -> List[OrganizationOut]:
    """Return active organizations only (reference catalog for authorized roles)."""
    rows = organization_repository.list_organizations(db, active_only=True)
    return [OrganizationOut.model_validate(r) for r in rows]


def list_divisions(db: Session, organization_id: Optional[int] = None) -> List[DivisionOut]:
    """
    Return active divisions.

    When organization_id is provided it must refer to an existing organization;
    unknown IDs are rejected (404) so callers cannot probe arbitrary IDs silently.
    """
    if organization_id is not None:
        org = organization_repository.get_organization_by_id(db, organization_id)
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        if not org.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
    rows = organization_repository.list_divisions(
        db, organization_id=organization_id, active_only=True
    )
    return [DivisionOut.model_validate(r) for r in rows]
