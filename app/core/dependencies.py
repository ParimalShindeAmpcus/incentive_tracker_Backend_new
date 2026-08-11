from collections.abc import Generator
from typing import Annotated, Callable, Iterable, Optional

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import verify_token
from app.db.session import get_db
from app.models.user import User
from app.repositories import user_repo

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    authorization: Annotated[Optional[str], Header()] = None,
) -> User:
    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise UnauthorizedError("Missing authentication token")
    try:
        payload = verify_token(token, expected_type="access")
    except ValueError as exc:
        raise UnauthorizedError(str(exc)) from exc
    user = user_repo.get_by_email(db, payload["sub"])
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: str) -> Callable:
    required = [r.upper() for r in roles]

    def _dependency(user: User = Depends(get_current_user)) -> User:
        user_roles = {r.name.upper() for r in user.roles}
        if "ADMIN" in user_roles:
            return user
        if not any(r in user_roles for r in required):
            raise ForbiddenError(f"Requires one of roles: {', '.join(required)}")
        return user

    return _dependency


def optional_roles(user: User, allowed: Iterable[str]) -> bool:
    names = {r.name.upper() for r in user.roles}
    if "ADMIN" in names:
        return True
    return any(a.upper() in names for a in allowed)
