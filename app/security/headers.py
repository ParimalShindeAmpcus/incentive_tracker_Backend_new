"""SEC-16: Security headers middleware.

Adds the following headers to every API response:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: strict-origin-when-cross-origin
  - Strict-Transport-Security  (only when hsts_enabled=True in settings)

NOTE on CSP:
  This is a JSON-only FastAPI backend; the React SPA is served separately.
  Adding Content-Security-Policy here would only affect API JSON responses and
  /docs (Swagger UI), not the React frontend.  A CSP on a JSON API provides
  minimal security value and can break Swagger UI's inline scripts/styles.
  CSP should be applied at the React frontend layer (via the Vite dev-server,
  a reverse proxy, or the SPA host's response headers).

NOTE on X-XSS-Protection:
  Intentionally omitted — the header is obsolete in modern browsers and can
  introduce vulnerabilities in older IE versions.  Modern XSS protection is
  provided by the browser's built-in XSS auditor and CSP (see above).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects HTTP security headers into every response.

    Args:
        app: The ASGI application to wrap.
        hsts_enabled: When True, adds the Strict-Transport-Security header.
                      Must only be True when the app is served over HTTPS.
        hsts_max_age: HSTS max-age in seconds (default 1 year = 31 536 000).
    """

    def __init__(self, app, *, hsts_enabled: bool = False, hsts_max_age: int = 31_536_000):
        super().__init__(app)
        self._hsts_enabled = hsts_enabled
        self._hsts_value = f"max-age={hsts_max_age}; includeSubDomains"

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # Prevent MIME-type sniffing attacks.
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Block the app from being embedded in iframes (clickjacking protection).
        response.headers["X-Frame-Options"] = "DENY"

        # Reduce referrer leakage to third-party sites.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS: only add when explicitly enabled (i.e. production HTTPS).
        # Never added for local HTTP development to avoid bricking the browser
        # for the localhost origin.
        if self._hsts_enabled:
            response.headers["Strict-Transport-Security"] = self._hsts_value

        return response
