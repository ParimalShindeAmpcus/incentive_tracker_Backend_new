"""Auth HTTP routes."""

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from app.config import get_settings
from app.models.auth.schemas import AuthResponse, LoginRequest, UserOut
from app.services.auth import auth_service
from app.services.common.deps import CurrentUser, DbSession

router = APIRouter()


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: DbSession, response: Response, request: Request) -> AuthResponse:
    fingerprint = auth_service.extract_client_fingerprint(request)
    access, refresh, user_out = auth_service.login(db, payload, client_fingerprint=fingerprint)
    settings = get_settings()
    secure = settings.environment != "development"
    response.set_cookie(key="access_token", value=access, httponly=True, secure=secure, samesite="lax", max_age=settings.access_token_expire_minutes * 60)
    response.set_cookie(key="refresh_token", value=refresh, httponly=True, secure=secure, samesite="lax", max_age=settings.refresh_token_expire_minutes * 60)
    
    # Return access_token in the body strictly for Swagger UI convenience in local dev
    return AuthResponse(
        user=user_out,
        access_token=access if settings.environment == "development" else None
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh(db: DbSession, response: Response, request: Request, refresh_token: str = Cookie(None)) -> AuthResponse:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")
    fingerprint = auth_service.extract_client_fingerprint(request)
    access, new_refresh, user_out = auth_service.refresh(db, refresh_token, client_fingerprint=fingerprint)
    settings = get_settings()
    secure = settings.environment != "development"
    response.set_cookie(key="access_token", value=access, httponly=True, secure=secure, samesite="lax", max_age=settings.access_token_expire_minutes * 60)
    response.set_cookie(key="refresh_token", value=new_refresh, httponly=True, secure=secure, samesite="lax", max_age=settings.refresh_token_expire_minutes * 60)
    return AuthResponse(user=user_out)


@router.post("/logout")
def logout(db: DbSession, request: Request, response: Response, refresh_token: str = Cookie(None)) -> dict:
    settings = get_settings()
    secure = settings.environment != "development"
    access_token = request.cookies.get("access_token")
    
    # Check Authorization header if cookie not present (for Swagger or legacy clients)
    if not access_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header[7:]

    response.delete_cookie(key="access_token", path="/", secure=secure, samesite="lax")
    response.delete_cookie(key="refresh_token", path="/", secure=secure, samesite="lax")
    return auth_service.logout(db, access_token, refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return auth_service.me(user)
