from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str,
    *,
    roles: Optional[Iterable[str]] = None,
    expires_minutes: Optional[int] = None,
    token_type: str = "access",
    extra: Optional[dict[str, Any]] = None,
) -> str:
    settings = get_settings()
    minutes = expires_minutes
    if minutes is None:
        minutes = (
            settings.access_token_expire_minutes
            if token_type == "access"
            else settings.refresh_token_expire_minutes
        )
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "roles": list(roles or []),
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, roles: Optional[Iterable[str]] = None) -> str:
    return create_access_token(subject, roles=roles, token_type="refresh")


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def verify_token(token: str, *, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
    if payload.get("type") != expected_type:
        raise ValueError("Invalid token type")
    if not payload.get("sub"):
        raise ValueError("Invalid token subject")
    return payload


def has_any_role(user_roles: Iterable[str], required: Iterable[str]) -> bool:
    required_set = {r.upper() for r in required}
    return any(r.upper() in required_set for r in user_roles)


def require_roles(user_roles: Iterable[str], required: Iterable[str]) -> None:
    if not has_any_role(user_roles, required):
        raise PermissionError("Insufficient role permissions")
