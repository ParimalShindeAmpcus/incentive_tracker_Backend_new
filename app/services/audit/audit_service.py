"""Audit service."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.audit.schemas import AuditLogOut
from app.repositories.audit import audit_repository


def list_logs(
    db: Session,
    *,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 100,
) -> List[AuditLogOut]:
    rows = audit_repository.list_logs(db, action=action, entity_type=entity_type, limit=limit)
    return [AuditLogOut.model_validate(r) for r in rows]


def write_log(db: Session, **kwargs) -> AuditLogOut:
    row = audit_repository.write_log(db, **kwargs)
    db.commit()
    db.refresh(row)
    return AuditLogOut.model_validate(row)
