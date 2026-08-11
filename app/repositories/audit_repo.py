from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditAction, AuditLog


def create(
    db: Session,
    *,
    action: AuditAction,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    row = AuditLog(
        action=action,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(row)
    db.flush()
    return row


def list_logs(
    db: Session,
    *,
    action: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[AuditLog]:
    q = db.query(AuditLog).order_by(AuditLog.id.desc())
    if action:
        q = q.filter(AuditLog.action == action)
    return q.offset(offset).limit(limit).all()


def count_logs(db: Session, *, action: Optional[str] = None) -> int:
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    return q.count()
