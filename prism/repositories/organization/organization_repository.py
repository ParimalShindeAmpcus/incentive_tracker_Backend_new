"""Organization repository — SQL only."""

from typing import List, Optional

from sqlalchemy.orm import Session

from prism.repositories.entities.organization import Division, Organization


def list_organizations(db: Session, active_only: bool = True) -> List[Organization]:
    q = db.query(Organization).order_by(Organization.name)
    if active_only:
        q = q.filter(Organization.is_active.is_(True))
    return q.all()


def list_divisions(
    db: Session,
    organization_id: Optional[int] = None,
    active_only: bool = True,
) -> List[Division]:
    q = db.query(Division).order_by(Division.name)
    if organization_id is not None:
        q = q.filter(Division.organization_id == organization_id)
    if active_only:
        q = q.filter(Division.is_active.is_(True))
    return q.all()


def get_organization_by_id(db: Session, organization_id: int) -> Optional[Organization]:
    return db.query(Organization).filter(Organization.id == organization_id).first()


def get_organization_by_code(db: Session, code: str) -> Optional[Organization]:
    return db.query(Organization).filter(Organization.code == code).first()


def create_organization(db: Session, code: str, name: str) -> Organization:
    org = Organization(code=code, name=name, is_active=True)
    db.add(org)
    db.flush()
    return org


def get_division_by_id(db: Session, division_id: int) -> Optional[Division]:
    return db.query(Division).filter(Division.id == division_id).first()


def get_division_by_code(db: Session, organization_id: int, code: str) -> Optional[Division]:
    return (
        db.query(Division)
        .filter(Division.organization_id == organization_id, Division.code == code)
        .first()
    )


def get_division_by_code_any_org(db: Session, code: str) -> Optional[Division]:
    return db.query(Division).filter(Division.code == code).first()


def create_division(
    db: Session,
    organization_id: int,
    code: str,
    name: str,
    description: Optional[str] = None,
    calculation_engine: Optional[str] = "MARGIN_SLABS_PRO_RATA",
    is_active: bool = True,
) -> Division:
    div = Division(
        organization_id=organization_id,
        code=code,
        name=name,
        description=description,
        calculation_engine=calculation_engine,
        is_active=is_active,
    )
    db.add(div)
    db.flush()
    return div

