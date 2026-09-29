"""Auth business logic."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mis.core.config import settings
from mis.core.constants import is_leadership_role
from mis.core.security import create_access_token, hash_password, verify_password
from mis.models.user import User
from mis.schemas.auth import TokenResponse, UserOut
from mis.services.password_reset_service import validate_password_strength

# Frontend workspace roles mapped from schema role codes
ROLE_CODE_TO_FRONTEND = {
    "RECRUITER": "recruiter",
    "MANAGER": "manager",
    "ONBOARD_TEAM": "onboard",
    "MIS": "admin",
    "HOD": "HOD",
    "TEAM_LEAD": "TEAM_LEAD",
    "CRM": "CRM",
    "SENIOR_MANAGER": "SENIOR_MANAGER",
    "ASSOCIATE_DIRECTOR": "ASSOCIATE_DIRECTOR",
    "DIRECTOR": "DIRECTOR",
    "CENTER_HEAD": "CENTER_HEAD",
    "AVP": "AVP",
}


def frontend_role_for_code(role_code: str) -> str:
    mapped = ROLE_CODE_TO_FRONTEND.get(role_code)
    if mapped:
        return mapped
    return role_code if is_leadership_role(role_code) else "recruiter"


def user_to_out(user: User) -> UserOut:
    role_code = user.role.code if user.role else ""
    return UserOut(
        id=user.id,
        email=str(user.email),
        full_name=user.full_name,
        role_code=role_code,
        role_label=frontend_role_for_code(role_code),
        organization_id=user.organization_id,
        organization_name=user.organization.name if user.organization else None,
        team_name=user.team_name,
        phone=user.phone,
        location=user.location,
        is_super_admin=user.is_super_admin,
        is_active=user.is_active,
    )


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.role), selectinload(User.organization))
        .where(func.lower(User.email) == email.lower().strip())
        .where(User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.role), selectinload(User.organization))
        .where(User.id == user_id)
        .where(User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> TokenResponse:
    user = await get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact an administrator.",
        )

    role_code = user.role.code if user.role else ""
    token = create_access_token(
        subject=user.id,
        extra_claims={
            "email": str(user.email),
            "role": role_code,
            "org_id": user.organization_id,
            "is_super_admin": user.is_super_admin,
        },
    )

    user_payload = user_to_out(user)
    user.last_login_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_payload,
    )


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    validate_password_strength(new_password)
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
