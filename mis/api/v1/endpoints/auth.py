from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mis.core.deps import get_current_user
from mis.core.constants import is_leadership_role
from mis.core.config import settings
from mis.core.security import create_access_token, verify_password
from mis.db.session import get_db
from mis.models import User
from mis.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    InvitationAcceptRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenValidationResponse,
)
from mis.schemas.user import LoginRequest, LoginResponse
from mis.services.auth_service import change_password
from mis.services.invitation_service import (
    accept_invitation_with_token,
    validate_invitation_token_for_db,
)
from mis.services.password_reset_service import (
    request_password_reset,
    reset_password_with_token,
    validate_reset_token,
)

router = APIRouter()

CODE_TO_FRONTEND_ROLE = {
    "RECRUITER": "recruiter",
    "MANAGER": "manager",
    "MIS": "admin",
    "ONBOARD_TEAM": "onboard",
    "HOD": "HOD",
    "TEAM_LEAD": "TEAM_LEAD",
    "CRM": "CRM",
    "SENIOR_MANAGER": "SENIOR_MANAGER",
    "ASSOCIATE_DIRECTOR": "ASSOCIATE_DIRECTOR",
    "DIRECTOR": "DIRECTOR",
    "CENTER_HEAD": "CENTER_HEAD",
    "AVP": "AVP",
}


def _frontend_role(role_code: str) -> str:
    mapped = CODE_TO_FRONTEND_ROLE.get(role_code)
    if mapped:
        return mapped
    return role_code if is_leadership_role(role_code) else "recruiter"


def _is_secure_request(request: Request) -> bool:
    return (
        settings.AUTH_COOKIE_SECURE
        or request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    email = body.email.strip().lower()
    password = body.password.strip()
    result = await db.execute(
        select(User)
        .options(selectinload(User.role))
        .where(func.lower(func.trim(User.email)) == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    token = create_access_token(user_id=user.id, email=user.email, role_code=user.role.code)
    is_secure = _is_secure_request(request)
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=is_secure,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )
    return LoginResponse(
        access_token=None,
        role=_frontend_role(user.role.code),
        role_code=user.role.code,
        name=user.full_name,
        email=user.email,
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    role_code = current_user.role.code if current_user.role else ""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "fullName": current_user.full_name,
        "roleCode": role_code,
        "roleLabel": _frontend_role(role_code),
        "organizationId": current_user.organization_id,
        "organizationName": current_user.organization.name if current_user.organization else None,
        "teamName": current_user.team_name,
        "phone": current_user.phone,
        "location": current_user.location,
        "isSuperAdmin": current_user.is_super_admin,
        "isActive": current_user.is_active,
    }


@router.post("/logout")
async def logout(response: Response, request: Request):
    is_secure = _is_secure_request(request)
    response.delete_cookie(
        settings.AUTH_COOKIE_NAME,
        path="/",
        secure=is_secure,
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    return {"message": "Logged out"}


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    message = await request_password_reset(db, str(body.email))
    return MessageResponse(message=message)


@router.get("/reset-password/validate", response_model=TokenValidationResponse)
async def validate_password_reset_token(
    token: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    valid = await validate_reset_token(db, token)
    return TokenValidationResponse(valid=valid)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    message = await reset_password_with_token(
        db,
        token=body.token,
        password=body.password,
        confirm_password=body.confirm_password,
    )
    return MessageResponse(message=message)


@router.put("/change-password", response_model=MessageResponse)
async def change_password_endpoint(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await change_password(db, current_user, body.current_password, body.new_password)
    return MessageResponse(message="Password updated successfully")


@router.get("/invitation/validate", response_model=TokenValidationResponse)
async def validate_invitation(
    token: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    valid = await validate_invitation_token_for_db(db, token)
    return TokenValidationResponse(valid=valid)


@router.post("/invitation/accept", response_model=MessageResponse)
async def accept_invitation(
    body: InvitationAcceptRequest,
    db: AsyncSession = Depends(get_db),
):
    message = await accept_invitation_with_token(
        db,
        token=body.token,
        password=body.password,
        confirm_password=body.confirm_password,
    )
    return MessageResponse(message=message)
