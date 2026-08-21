"""Audit HTTP routes."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Query

from app.models.audit.schemas import AuditLogCreate, AuditLogOut
from app.repositories.entities.audit import AuditAction
from app.services.audit import audit_service
from app.services.common.deps import CurrentUser, DbSession

router = APIRouter()


@router.get("/logs", response_model=List[AuditLogOut])
def get_logs(
    db: DbSession,
    user: CurrentUser,
    action: Optional[AuditAction] = Query(None),
    search: Optional[str] = Query(None),
    year: Optional[int] = Query(None, ge=1900, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    skip: int = Query(0, ge=0),
) -> List[AuditLogOut]:
    return audit_service.list_logs(
        db,
        action=action.value if action else None,
        search=search,
        year=year,
        month=month,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        skip=skip,
    )


@router.post("/logs", response_model=AuditLogOut, status_code=201)
def create_log(
    payload: AuditLogCreate,
    db: DbSession,
    user: CurrentUser,
) -> AuditLogOut:
    return audit_service.create_log(db, payload, user)
