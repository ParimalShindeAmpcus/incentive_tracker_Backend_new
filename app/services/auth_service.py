from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    verify_token,
)
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import audit_repo, user_repo
from app.schemas.auth import TokenResponse, UserOut


def _roles(user: User) -> list[str]:
    return [r.name for r in user.roles]


def login(db: Session, email: str, password: str) -> TokenResponse:
    user = user_repo.get_by_email(db, email.lower().strip())
    if not user or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedError("User is inactive")
    roles = _roles(user)
    tokens = TokenResponse(
        access_token=create_access_token(user.email, roles=roles),
        refresh_token=create_refresh_token(user.email, roles=roles),
    )
    audit_repo.create(
        db,
        action=AuditAction.LOGIN,
        user_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        details=f"Login by {user.email}",
    )
    db.commit()
    return tokens


def refresh(db: Session, refresh_token: str) -> TokenResponse:
    try:
        payload = verify_token(refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise UnauthorizedError(str(exc)) from exc
    user = user_repo.get_by_email(db, payload["sub"])
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    roles = _roles(user)
    return TokenResponse(
        access_token=create_access_token(user.email, roles=roles),
        refresh_token=create_refresh_token(user.email, roles=roles),
    )


def logout(db: Session, user: User) -> dict:
    audit_repo.create(
        db,
        action=AuditAction.UPDATE,
        user_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        details="Logout",
    )
    db.commit()
    return {"success": True, "message": "Logged out"}


def me(user: User) -> UserOut:
    return UserOut.model_validate(user)
