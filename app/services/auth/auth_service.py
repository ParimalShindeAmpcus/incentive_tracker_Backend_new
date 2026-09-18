"""Auth service — orchestration."""

from datetime import datetime, timedelta, timezone

from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.auth.schemas import LoginRequest, UserOut
from app.repositories.auth import auth_repository
from app.repositories.entities.user import User
from app.security.auth import (
    compute_client_fingerprint,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)


_login_attempts: dict[str, tuple[int, datetime]] = {}


def extract_client_fingerprint(request: Optional[Request]) -> Optional[str]:
    """Extract client fingerprint from request headers."""
    if request is None:
        return None
    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else ""
    return compute_client_fingerprint(user_agent=user_agent, client_ip=client_ip)


def login(db: Session, payload: LoginRequest, client_fingerprint: Optional[str] = None) -> tuple[str, str, UserOut]:
    settings = get_settings()
    key = payload.email.lower().strip()
    now = datetime.now(timezone.utc)
    attempt_count, first_seen = _login_attempts.get(key, (0, now))
    if attempt_count >= int(getattr(settings, "max_failed_login_attempts", 5)) and now - first_seen < timedelta(minutes=int(getattr(settings, "lockout_minutes", 15))):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed login attempts. Please try again later.")

    user = auth_repository.get_user_by_email(db, key)
    if user is None or not verify_password(payload.password, user.hashed_password):
        failed_count = attempt_count + 1
        _login_attempts[key] = (failed_count, first_seen)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")

    _login_attempts.pop(key, None)
    access = create_access_token(str(user.id), {"email": user.email})
    extra = {"fpt": client_fingerprint} if client_fingerprint else None
    refresh = create_refresh_token(str(user.id), extra=extra)
    return access, refresh, UserOut.model_validate(user)


def refresh(db: Session, refresh_token: str, client_fingerprint: Optional[str] = None) -> tuple[str, str, UserOut]:
    try:
        payload = decode_token(refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    sub = payload.get("sub")
    jti = payload.get("jti")
    exp = payload.get("exp")
    fpt = payload.get("fpt")
    if not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token structure")

    if auth_repository.is_token_revoked(db, jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")

    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    # Validate device / session fingerprint if present
    if fpt and client_fingerprint and fpt != client_fingerprint:
        # Mismatch indicates potential session hijacking/token theft -> Revoke token immediately
        if exp:
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
            auth_repository.revoke_token(db, jti=jti, token_type="refresh", expires_at=expires_at, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session fingerprint mismatch. Token revoked.",
        )

    user = auth_repository.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Revoke the used refresh token (refresh token rotation)
    if exp:
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        auth_repository.revoke_token(db, jti=jti, token_type="refresh", expires_at=expires_at, user_id=user_id)

    access = create_access_token(str(user.id), {"email": user.email})
    new_fpt = client_fingerprint or fpt
    extra = {"fpt": new_fpt} if new_fpt else None
    new_refresh = create_refresh_token(str(user.id), extra=extra)
    return access, new_refresh, UserOut.model_validate(user)


def me(user: User) -> UserOut:
    return UserOut.model_validate(user)


def logout(db: Session, access_token: str | None = None, refresh_token: str | None = None) -> dict:
    """Logout — revoke access and refresh tokens."""
    import jose.jwt
    
    auth_repository.cleanup_expired_tokens(db)
    
    for token in (access_token, refresh_token):
        if not token:
            continue
        try:
            # Decode without verifying expiration so we can still extract jti if it's not expired
            payload = jose.jwt.get_unverified_claims(token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            token_type = payload.get("type", "unknown")
            sub = payload.get("sub")
            if jti and exp:
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
                # If already expired, no need to store in revoked table
                if expires_at > datetime.now(timezone.utc):
                    user_id = int(sub) if sub and str(sub).isdigit() else None
                    auth_repository.revoke_token(
                        db, jti=jti, token_type=token_type, expires_at=expires_at, user_id=user_id
                    )
        except Exception:
            pass  # Malformed tokens can be safely ignored during logout
            
    return {"message": "logged out"}
