"""Audit service."""

from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session

from app.models.audit.schemas import AuditLogCreate, AuditLogOut
from app.repositories.audit import audit_repository
from app.repositories.entities.audit import AuditAction, AuditLog
from app.repositories.entities.user import User


def _username_from_user(user: User) -> str:
    email = (user.email or "").strip()
    if "@" in email:
        return email.split("@", 1)[0]
    return email or "unknown"


def _user_display_from_user(user: User) -> str:
    if user.full_name:
        return user.full_name
    if user.roles:
        return user.roles[0].name
    return "Accounts Department"


def list_logs(
    db: Session,
    *,
    action: Optional[str] = None,
    search: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 500,
    skip: int = 0,
) -> List[AuditLogOut]:
    rows = audit_repository.list_logs(
        db,
        action=action,
        search=search,
        year=year,
        month=month,
        limit=limit,
        skip=skip,
    )
    return [AuditLogOut.from_orm_row(r) for r in rows]


def record_event(
    db: Session,
    *,
    action: Union[AuditAction, str],
    title: str,
    details: str,
    user: Optional[User] = None,
    metadata: Optional[Dict[str, Any]] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> AuditLog:
    """Write an audit row in the caller's transaction. Does not commit."""
    user_display = _user_display_from_user(user) if user is not None else "system"
    username = _username_from_user(user) if user is not None else "system"
    return audit_repository.write_log(
        db,
        action=action,
        title=title,
        details=details,
        user_display=user_display,
        username=username,
        metadata=metadata,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user.id if user is not None else None,
    )


def create_log(db: Session, payload: AuditLogCreate, user: User) -> AuditLogOut:
    user_display = payload.user or _user_display_from_user(user)
    username = payload.username or _username_from_user(user)
    row = audit_repository.write_log(
        db,
        action=payload.action,
        title=payload.title,
        details=payload.details,
        user_display=user_display,
        username=username,
        metadata=payload.metadata,
        user_id=user.id,
    )
    db.commit()
    db.refresh(row)
    return AuditLogOut.from_orm_row(row)


def record_event(
    db: Session,
    *,
    action: AuditAction,
    title: str,
    details: str,
    user: Optional[User] = None,
    metadata: Optional[dict[str, Any]] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> None:
    """Record an internal audit event; the surrounding service owns the commit."""
    user_display = _user_display_from_user(user) if user else "System"
    username = _username_from_user(user) if user else "system"
    audit_repository.write_log(
        db,
        action=action,
        title=title,
        details=details,
        user_display=user_display,
        username=username,
        metadata=metadata,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user.id if user else None,
    )
