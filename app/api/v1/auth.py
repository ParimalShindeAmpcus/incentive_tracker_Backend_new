from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession):
    return auth_service.login(db, payload.email, payload.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: DbSession):
    return auth_service.refresh(db, payload.refresh_token)


@router.post("/logout")
def logout(db: DbSession, user: CurrentUser):
    return auth_service.logout(db, user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER"))):
    return auth_service.me(user)
