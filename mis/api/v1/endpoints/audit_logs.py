from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import require_roles
from mis.db.session import get_db
from mis.models import User
from mis.services.audit_service import list_audit_logs

router = APIRouter()

AdminUser = Annotated[User, Depends(require_roles("MIS"))]


@router.get("")
async def get_audit_logs(
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
    entity_type: str | None = Query(None, alias="entityType"),
    activity_id: str | None = Query(None, alias="activityId"),
    from_date: str | None = Query(None, alias="fromDate"),
    to_date: str | None = Query(None, alias="toDate"),
    limit: int = Query(200, ge=1, le=500),
):
    # Super admins have global visibility; all other admins are scoped to their own org.
    org_filter = None if _admin.is_super_admin else _admin.organization_id
    return await list_audit_logs(
        db,
        limit=limit,
        organization_id=org_filter,
        entity_type=entity_type,
        activity_id=activity_id,
        from_date=from_date,
        to_date=to_date,
    )
