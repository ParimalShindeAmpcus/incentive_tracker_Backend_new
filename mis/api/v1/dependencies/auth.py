"""Auth dependencies: current user + role guards."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.security import decode_access_token
from mis.db.session import get_db
from mis.models.user import User
from mis.services.auth_service import get_user_by_id

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session_cookie: str | None = Cookie(default=None, alias="mis_session"),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else session_cookie
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*allowed_role_codes: str) -> Callable:
    """Dependency factory: allow only users whose role.code is in allowed_role_codes.

    Example: Depends(require_roles("MIS", "MANAGER"))
    Super-admins (is_super_admin) always pass.
    """

    allowed = {code.upper() for code in allowed_role_codes}

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.is_super_admin:
            return user
        role_code = (user.role.code if user.role else "").upper()
        if role_code not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(sorted(allowed))}",
            )
        return user

    return _checker
