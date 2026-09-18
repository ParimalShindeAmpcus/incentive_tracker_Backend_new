"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.security.headers import SecurityHeadersMiddleware

from app.config import get_settings
from app.controllers.audit.controller import router as audit_router
from app.controllers.auth.controller import router as auth_router
from app.controllers.candidates.controller import router as candidates_router
from app.controllers.cycles.controller import router as cycles_router
from app.controllers.dashboard.controller import router as dashboard_router
from app.controllers.health.controller import router as health_router
from app.controllers.hours.controller import benchmarks_router as hours_benchmarks_router
from app.controllers.hours.controller import router as hours_router
from app.controllers.incentives.controller import router as incentives_router
from app.controllers.organization.controller import router as organization_router
from app.controllers.project_end.controller import router as project_end_router
from app.controllers.coordinators.controller import router as coordinators_router
from app.controllers.reports.controller import router as reports_router
from app.controllers.vlookup.controller import router as vlookup_router
from app.core.db import init_db
from app.services.common.seed import seed_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    try:
        init_db()
        if settings.seed_on_startup:
            seed_database()
    except Exception as exc:
        # Keep /health available when DB is unreachable during local/test startup
        logger.warning("Startup init_db/seed skipped: %s", exc)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    prefix = settings.api_v1_prefix
    _is_prod = settings.environment.lower() in {"production", "prod"}
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if _is_prod else "/docs",
        redoc_url=None if _is_prod else "/redoc",
        openapi_url=None if _is_prod else "/openapi.json",
    )
    # Explicit origin allowlist only (from CORS_ORIGINS). No wildcard / intranet regex.
    cors_origins = settings.get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    # SEC-16: add security headers to every response.
    # Registered after CORS so it wraps the outermost layer and stamps headers
    # on all responses, including error and 404 responses from Starlette itself.
    # Enforces CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
    # X-XSS-Protection, and Strict-Transport-Security (HSTS).
    app.add_middleware(
        SecurityHeadersMiddleware,
        hsts_enabled=settings.hsts_enabled,
        hsts_max_age=settings.hsts_max_age,
        csp_policy=settings.csp_policy,
    )

    @app.get("/")
    def root():
        """Minimal root response — no app/docs/api surface disclosure."""
        return {"status": "ok"}

    # Canonical health check — lightweight process liveness (no auth).
    # Do not remount under /api/v1/health; that duplicate triggered security audits
    # and is unused by Docker/K8s/frontend/docs (all use GET /health).
    app.include_router(health_router, prefix="/health", tags=["health"])

    app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["auth"])
    app.include_router(dashboard_router, prefix=f"{prefix}/dashboard", tags=["dashboard"])
    app.include_router(organization_router, prefix=prefix, tags=["organization"])
    app.include_router(candidates_router, prefix=prefix, tags=["candidates"])
    app.include_router(coordinators_router, prefix=f"{prefix}/coordinators", tags=["coordinators"])
    app.include_router(hours_router, prefix=f"{prefix}/hours-data", tags=["hours"])
    app.include_router(hours_benchmarks_router, prefix=f"{prefix}/hours-benchmarks", tags=["hours-benchmarks"])
    app.include_router(project_end_router, prefix=f"{prefix}/project-end", tags=["project-end"])
    app.include_router(cycles_router, prefix=f"{prefix}/cycles", tags=["cycles"])
    app.include_router(incentives_router, prefix=prefix, tags=["incentives"])
    app.include_router(audit_router, prefix=f"{prefix}/audit", tags=["audit"])
    app.include_router(vlookup_router, prefix=f"{prefix}/vlookup", tags=["vlookup"])
    app.include_router(reports_router, prefix=prefix, tags=["reports"])

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred. Please contact the system administrator."},
        )

    return app


app = create_app()

__all__ = ["create_app", "app", "SecurityHeadersMiddleware"]
