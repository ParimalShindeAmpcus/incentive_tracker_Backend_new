from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mis.core.deps import get_current_user
from mis.db.session import get_db
from mis.models import Role, User
from mis.schemas.user import UserRead

router = APIRouter()


@router.get("", response_model=list[UserRead])
async def list_recruiters(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    role: str | None = Query(None, description="Filter by role code: MANAGER, TEAM_LEAD, RECRUITER, MIS"),
    organization_id: int | None = Query(None, description="Filter by organization ID"),
):
    """Active users for form people-directory dropdowns."""
    stmt = (
        select(User)
        .options(selectinload(User.role), selectinload(User.organization))
        .where(User.deleted_at.is_(None), User.is_active.is_(True))
        .order_by(User.full_name)
    )
    if organization_id is not None:
        stmt = stmt.where(User.organization_id == organization_id)
    if role:
        stmt = stmt.join(User.role).where(Role.code == role.strip().upper())

    result = await db.execute(stmt)
    users = result.scalars().all()
    return [
        UserRead(
            id=u.id,
            organization_id=u.organization_id,
            role_code=u.role.code,
            full_name=u.full_name,
            email=u.email,
            team_name=u.team_name,
            phone=u.phone,
            location=u.location,
            is_active=u.is_active,
            is_super_admin=u.is_super_admin,
            organization_name=u.organization.name if u.organization else None,
        )
        for u in users
    ]
