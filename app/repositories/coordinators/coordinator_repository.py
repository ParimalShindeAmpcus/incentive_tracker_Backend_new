from typing import Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus

def get(db: Session, record_id: int): return db.get(CoordinatorRecord, record_id)
def by_email(db: Session, email: str): return db.query(CoordinatorRecord).filter(CoordinatorRecord.email == email.lower()).first()
def query(db: Session, search: Optional[str] = None, status: Optional[CoordinatorStatus] = None):
    q = db.query(CoordinatorRecord)
    if search:
        term = f"%{search.strip()}%"; q = q.filter(or_(CoordinatorRecord.full_name.ilike(term), CoordinatorRecord.email.ilike(term), CoordinatorRecord.organization.ilike(term), CoordinatorRecord.role_title.ilike(term)))
    if status: q = q.filter(CoordinatorRecord.employment_status == status)
    return q
def list_records(db: Session, offset: int, limit: int, search: Optional[str] = None, status: Optional[CoordinatorStatus] = None): return query(db, search, status).order_by(CoordinatorRecord.full_name).offset(offset).limit(limit).all()
def count(db: Session, search: Optional[str] = None, status: Optional[CoordinatorStatus] = None): return query(db, search, status).count()
def counts(db: Session):
    result = {item.value: 0 for item in CoordinatorStatus}
    for status, count in db.query(CoordinatorRecord.employment_status, func.count(CoordinatorRecord.id)).group_by(CoordinatorRecord.employment_status).all(): result[status.value] = count
    return result
