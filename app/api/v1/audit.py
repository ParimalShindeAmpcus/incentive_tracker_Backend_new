from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
def list_audit_logs(
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
    action: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    return audit_service.list_logs(db, action=action, page=page, page_size=page_size)
