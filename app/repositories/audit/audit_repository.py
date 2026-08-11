"""Audit repository — SQL only."""

from typing import List, Optional, Union

from sqlalchemy.orm import Session

from app.repositories.entities.audit import AuditAction, AuditLog


def list_logs(
    db: Session,
    *,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
) -> List[AuditLog]:
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == AuditAction(action))
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    return q.order_by(AuditLog.id.desc()).offset(skip).limit(limit).all()


def write_log(
    db: Session,
    *,
    action: Union[AuditAction, str],
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    user_id: Optional[int] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    action_enum = action if isinstance(action, AuditAction) else AuditAction(action)
    row = AuditLog(
        action=action_enum,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(row)
    db.flush()
    return row
