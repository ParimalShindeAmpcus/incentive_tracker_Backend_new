"""Audit HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.models.audit.schemas import AuditLogOut
from app.services.audit import audit_service
from app.services.common.deps import DbSession

router = APIRouter()


@router.get("/logs", response_model=List[AuditLogOut])
def get_logs(
    db: DbSession,
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> List[AuditLogOut]:
    return audit_service.list_logs(db, action=action, entity_type=entity_type, limit=limit)
