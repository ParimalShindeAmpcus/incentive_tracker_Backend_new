"""SEC-16: Security headers middleware.

Adds comprehensive HTTP security headers to every API response:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: strict-origin-when-cross-origin
  - Strict-Transport-Security: max-age=...; includeSubDomains
  - X-XSS-Protection: 1; mode=block
  - Content-Security-Policy: default-src 'self'; ...
"""

from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

DEFAULT_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects HTTP security headers into every response.

    Args:
        app: The ASGI application to wrap.
        hsts_enabled: When True, adds the Strict-Transport-Security header.
                      Defaults to True for security compliance.
        hsts_max_age: HSTS max-age in seconds (default 1 year = 31 536 000).
        csp_policy: Content-Security-Policy header string. Defaults to DEFAULT_CSP_POLICY.
        x_frame_options: X-Frame-Options header value. Defaults to "DENY".
        x_content_type_options: X-Content-Type-Options value. Defaults to "nosniff".
        x_xss_protection: X-XSS-Protection value. Defaults to "1; mode=block".
        referrer_policy: Referrer-Policy value. Defaults to "strict-origin-when-cross-origin".
    """

    def __init__(
        self,
        app,
        *,
        hsts_enabled: bool = True,
        hsts_max_age: int = 31_536_000,
        csp_policy: Optional[str] = DEFAULT_CSP_POLICY,
        x_frame_options: str = "DENY",
        x_content_type_options: str = "nosniff",
        x_xss_protection: str = "1; mode=block",
        referrer_policy: str = "strict-origin-when-cross-origin",
    ):
        super().__init__(app)
        self._hsts_enabled = hsts_enabled
        self._hsts_value = f"max-age={hsts_max_age}; includeSubDomains"
        self._csp_policy = csp_policy
        self._x_frame_options = x_frame_options
        self._x_content_type_options = x_content_type_options
        self._x_xss_protection = x_xss_protection
        self._referrer_policy = referrer_policy

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # 1. Prevent MIME-type sniffing attacks.
        if self._x_content_type_options:
            response.headers["X-Content-Type-Options"] = self._x_content_type_options

        # 2. Block the app from being embedded in iframes (clickjacking protection).
        if self._x_frame_options:
            response.headers["X-Frame-Options"] = self._x_frame_options

        # 3. Reduce referrer leakage to third-party sites.
        if self._referrer_policy:
            response.headers["Referrer-Policy"] = self._referrer_policy

        # 4. Cross-site scripting filter (standard security audit requirement).
        if self._x_xss_protection:
            response.headers["X-XSS-Protection"] = self._x_xss_protection

        # 5. Content-Security-Policy (CSP).
        if self._csp_policy:
            response.headers["Content-Security-Policy"] = self._csp_policy

        # 6. Strict-Transport-Security (HSTS):
        # Injected when hsts_enabled=True or when the request was made over HTTPS.
        if (
            self._hsts_enabled
            or request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https"
        ):
            response.headers["Strict-Transport-Security"] = self._hsts_value

        return response
