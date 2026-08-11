from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.recruiter import RecruiterMasterVersion, RecruiterStatus
from app.models.organization import Employee


def create_version(db: Session, **kwargs) -> RecruiterMasterVersion:
    row = RecruiterMasterVersion(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_version(db: Session, version_id: int) -> Optional[RecruiterMasterVersion]:
    return db.query(RecruiterMasterVersion).filter(RecruiterMasterVersion.id == version_id).first()


def list_versions(db: Session, *, offset: int = 0, limit: int = 50) -> List[RecruiterMasterVersion]:
    return (
        db.query(RecruiterMasterVersion)
        .order_by(RecruiterMasterVersion.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def add_status(db: Session, **kwargs) -> RecruiterStatus:
    row = RecruiterStatus(**kwargs)
    db.add(row)
    db.flush()
    return row


def list_statuses(db: Session, version_id: int) -> List[RecruiterStatus]:
    return db.query(RecruiterStatus).filter(RecruiterStatus.version_id == version_id).all()


def find_employee_by_name(db: Session, normalized_name: str) -> Optional[Employee]:
    return db.query(Employee).filter(Employee.normalized_name == normalized_name).first()


def create_employee(db: Session, **kwargs) -> Employee:
    row = Employee(**kwargs)
    db.add(row)
    db.flush()
    return row
