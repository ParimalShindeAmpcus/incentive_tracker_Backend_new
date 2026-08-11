from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditAction
from app.repositories import audit_repo
from app.utils.pagination import paginate


def write(
    db: Session,
    *,
    action: AuditAction,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[str] = None,
    commit: bool = False,
):
    row = audit_repo.create(
        db,
        action=action,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    if commit:
        db.commit()
    return row


def list_logs(db: Session, *, action: Optional[str] = None, page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    rows = audit_repo.list_logs(db, action=action, offset=offset, limit=page_size)
    total = audit_repo.count_logs(db, action=action)
    data = [
        {
            "id": r.id,
            "action": r.action.value if hasattr(r.action, "value") else str(r.action),
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "user_id": r.user_id,
            "details": r.details,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return paginate(data, total, page, page_size)
