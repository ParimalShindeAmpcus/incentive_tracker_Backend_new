"""JWT and password helpers."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def compute_client_fingerprint(user_agent: Optional[str] = None, client_ip: Optional[str] = None) -> str:
    """Compute client fingerprint from user-agent to bind refresh tokens."""
    raw = f"{user_agent or 'unknown'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(data: Dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
    settings = get_settings()
    payload = data.copy()
    now = datetime.now(timezone.utc)
    payload.update(
        {
            "exp": now + expires_delta,
            "iat": now,
            "type": token_type,
            "jti": uuid.uuid4().hex,
        }
    )
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str, extra: Optional[Dict[str, Any]] = None) -> str:
    settings = get_settings()
    data: Dict[str, Any] = {"sub": subject}
    if extra:
        data.update(extra)
    return _create_token(
        data,
        timedelta(minutes=settings.access_token_expire_minutes),
        "access",
    )


def create_refresh_token(subject: str, extra: Optional[Dict[str, Any]] = None) -> str:
    settings = get_settings()
    data: Dict[str, Any] = {"sub": subject}
    if extra:
        data.update(extra)
    return _create_token(
        data,
        timedelta(minutes=settings.refresh_token_expire_minutes),
        "refresh",
    )


def decode_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
