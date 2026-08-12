"""Audit repository — SQL only."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import String, cast, extract, or_
from sqlalchemy.orm import Session

from app.repositories.entities.audit import AuditAction, AuditLog


def list_logs(
    db: Session,
    *,
    action: Optional[str] = None,
    search: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 500,
    skip: int = 0,
) -> List[AuditLog]:
    q = db.query(AuditLog)

    if action:
        q = q.filter(AuditLog.action == AuditAction(action))

    if year is not None:
        q = q.filter(extract("year", AuditLog.created_at) == year)

    if month is not None:
        q = q.filter(extract("month", AuditLog.created_at) == month)

    if search:
        term = search.strip()
        if term.upper().startswith("LOG-"):
            try:
                log_id = int(term.upper().replace("LOG-", ""))
                q = q.filter(AuditLog.id == log_id)
            except ValueError:
                pass
        else:
            ilike_term = f"%{term.lower()}%"
            log_id_expr = cast(AuditLog.id, String)
            q = q.filter(
                or_(
                    AuditLog.title.ilike(ilike_term),
                    AuditLog.details.ilike(ilike_term),
                    AuditLog.user_display.ilike(ilike_term),
                    AuditLog.username.ilike(ilike_term),
                    log_id_expr.ilike(ilike_term),
                )
            )

    return q.order_by(AuditLog.id.desc()).offset(skip).limit(limit).all()


def count_logs(db: Session) -> int:
    return db.query(AuditLog).count()


def write_log(
    db: Session,
    *,
    action: Union[AuditAction, str],
    title: str,
    details: str,
    user_display: str = "",
    username: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> AuditLog:
    action_enum = action if isinstance(action, AuditAction) else AuditAction(action)
    row = AuditLog(
        action=action_enum,
        title=title,
        details=details,
        user_display=user_display,
        username=username,
        metadata_json=metadata,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        ip_address=ip_address,
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.flush()
    return row
