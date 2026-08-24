"""Audit service."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.audit.schemas import AuditLogCreate, AuditLogOut
from app.repositories.audit import audit_repository
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
