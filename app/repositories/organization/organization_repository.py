"""Organization repository — SQL only."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.repositories.entities.organization import Division, Employee, Organization


def list_organizations(db: Session, active_only: bool = False) -> List[Organization]:
    q = db.query(Organization).order_by(Organization.name)
    if active_only:
        q = q.filter(Organization.is_active.is_(True))
    return q.all()


def list_divisions(
    db: Session,
    organization_id: Optional[int] = None,
    active_only: bool = False,
) -> List[Division]:
    q = db.query(Division).order_by(Division.name)
    if organization_id is not None:
        q = q.filter(Division.organization_id == organization_id)
    if active_only:
        q = q.filter(Division.is_active.is_(True))
    return q.all()


def list_employees(
    db: Session,
    division_id: Optional[int] = None,
    active_only: bool = False,
) -> List[Employee]:
    q = db.query(Employee).order_by(Employee.full_name)
    if division_id is not None:
        q = q.filter(Employee.division_id == division_id)
    if active_only:
        q = q.filter(Employee.is_active.is_(True))
    return q.all()


def get_organization_by_code(db: Session, code: str) -> Optional[Organization]:
    return db.query(Organization).filter(Organization.code == code).first()


def create_organization(db: Session, code: str, name: str) -> Organization:
    org = Organization(code=code, name=name, is_active=True)
    db.add(org)
    db.flush()
    return org


def get_division_by_code(db: Session, organization_id: int, code: str) -> Optional[Division]:
    return (
        db.query(Division)
        .filter(Division.organization_id == organization_id, Division.code == code)
        .first()
    )


def create_division(db: Session, organization_id: int, code: str, name: str) -> Division:
    div = Division(organization_id=organization_id, code=code, name=name, is_active=True)
    db.add(div)
    db.flush()
    return div
