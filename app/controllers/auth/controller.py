"""Auth HTTP routes."""

from fastapi import APIRouter

from app.models.auth.schemas import LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.services.auth import auth_service
from app.services.common.deps import CurrentUser, DbSession

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    return auth_service.login(db, payload)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    return auth_service.refresh(db, payload.refresh_token)


@router.post("/logout")
def logout() -> dict:
    return auth_service.logout()


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return auth_service.me(user)
