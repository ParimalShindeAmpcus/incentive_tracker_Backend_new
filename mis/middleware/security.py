from collections import defaultdict, deque
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from mis.core.config import settings


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        limited_paths = {
            "/api/v1/auth/login",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/reset-password/validate",
            "/api/v1/auth/reset-password",
            "/api/v1/auth/invitation/validate",
            "/api/v1/auth/invitation/accept",
        }
        if path in limited_paths:
            bucket = "login" if path.endswith("/login") else "reset"
            limit = settings.RATE_LIMIT_LOGIN_MAX if bucket == "login" else settings.RATE_LIMIT_RESET_MAX
            key = (bucket, request.client.host if request.client else "unknown")
            now = monotonic()
            timestamps = self._requests[key]
            while timestamps and now - timestamps[0] >= settings.RATE_LIMIT_WINDOW_SECONDS:
                timestamps.popleft()
            if len(timestamps) >= limit:
                return JSONResponse({"detail": "Too many requests"}, status_code=429)
            timestamps.append(now)

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if path in ("/docs", "/redoc", "/openapi.json"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'none'",
            )
        else:
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response