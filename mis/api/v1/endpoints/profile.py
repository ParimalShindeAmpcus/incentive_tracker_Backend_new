from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import get_current_user
from mis.db.session import get_db
from mis.models.user import User
from mis.schemas.auth import ProfileUpdate
from mis.services import auth_service

router = APIRouter()


def _profile_payload(user: User) -> dict:
    role_code = user.role.code if user.role else ""
    return {
        "id": user.id,
        "email": user.email,
        "fullName": user.full_name,
        "roleCode": role_code,
        "roleLabel": auth_service.frontend_role_for_code(role_code),
        "organizationId": user.organization_id,
        "organizationName": user.organization.name if user.organization else None,
        "teamName": user.team_name,
        "phone": user.phone,
        "location": user.location,
        "isSuperAdmin": user.is_super_admin,
        "isActive": user.is_active,
    }


@router.get("")
async def get_profile(current_user: User = Depends(get_current_user)):
    return _profile_payload(current_user)


@router.put("")
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name.strip()
    if body.phone is not None:
        current_user.phone = body.phone.strip() or None
    if body.location is not None:
        current_user.location = body.location.strip() or None
    current_user.updated_by = current_user.id
    await db.commit()
    await db.refresh(current_user, ["role", "organization"])
    return _profile_payload(current_user)

