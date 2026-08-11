"""Auth service — orchestration."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.auth.schemas import LoginRequest, TokenResponse, UserOut
from app.repositories.auth import auth_repository
from app.repositories.entities.user import User
from app.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)


def login(db: Session, payload: LoginRequest) -> TokenResponse:
    user = auth_repository.get_user_by_email(db, payload.email.lower().strip())
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")

    access = create_access_token(str(user.id), {"email": user.email})
    refresh = create_refresh_token(str(user.id))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
    )


def refresh(db: Session, refresh_token: str) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    sub = payload.get("sub")
    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    user = auth_repository.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    access = create_access_token(str(user.id), {"email": user.email})
    new_refresh = create_refresh_token(str(user.id))
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        user=UserOut.model_validate(user),
    )


def me(user: User) -> UserOut:
    return UserOut.model_validate(user)


def logout() -> dict:
    """Logout stub — client discards tokens (stateless JWT)."""
    return {"message": "logged out"}
