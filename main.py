"""Unified FastAPI application entrypoint for MIS & PRISM Platform."""

import asyncio
from contextlib import asynccontextmanager
import logging
import sys
from pathlib import Path
from typing import Optional

# Ensure project root is in python path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Fix for passlib compatibility with bcrypt >= 4.1.0
try:
    import bcrypt
    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = type("about", (), {"__version__": getattr(bcrypt, "__version__", "4.0.0")})
except Exception:
    pass

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

# Import MIS modules
from mis.api.v1.router import api_router as mis_router
from mis.core.config import settings as mis_settings
from mis.core.security import create_access_token as mis_create_access_token, verify_password as mis_verify_password
from mis.db.session import engine as mis_engine
from mis.models import User as MisUser
from mis.services.email_ingestion.pipeline import run_email_ingestion_pipeline
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

# Import PRISM modules
from prism.config import get_settings as get_prism_settings
from prism.controllers.audit.controller import router as prism_audit_router
from prism.controllers.auth.controller import router as prism_auth_router
from prism.controllers.candidates.controller import router as prism_candidates_router
from prism.controllers.coordinators.controller import router as prism_coordinators_router
from prism.controllers.cycles.controller import router as prism_cycles_router
from prism.controllers.dashboard.controller import router as prism_dashboard_router
from prism.controllers.hours.controller import benchmarks_router as prism_hours_benchmarks_router, router as prism_hours_router
from prism.controllers.incentives.controller import router as prism_incentives_router
from prism.controllers.organization.controller import router as prism_organization_router
from prism.controllers.project_end.controller import router as prism_project_end_router
from prism.controllers.reports.controller import router as prism_reports_router
from prism.controllers.special_incentive.controller import router as prism_special_incentive_router
from prism.controllers.vlookup.controller import router as prism_vlookup_router
from prism.core.db import get_engine as get_prism_engine, init_db as init_prism_db
from prism.models.auth.schemas import LoginRequest as PrismLoginRequest
from prism.security.headers import SecurityHeadersMiddleware
from prism.services.auth import auth_service as prism_auth_service
from prism.services.common.seed import seed_database as seed_prism_database

logger = logging.getLogger("mis_prism.unified")
logging.basicConfig(level=logging.INFO)


async def mis_email_ingestion_scheduler():
    """Background task for MIS email ingestion pipeline."""
    if not mis_settings.EMAIL_INGESTION_ENABLED:
        logger.info("MIS Email Ingestion background scheduler is disabled.")
        return

    interval_minutes = max(mis_settings.EMAIL_INGESTION_INTERVAL_MINUTES, 1)
    interval_seconds = interval_minutes * 60
    logger.info("MIS Email Ingestion scheduler started (%d min interval).", interval_minutes)

    while True:
        try:
            logger.info("Triggering scheduled MIS Email Ingestion Pipeline...")
            await asyncio.to_thread(run_email_ingestion_pipeline)
        except asyncio.CancelledError:
            logger.info("MIS Email Ingestion scheduler task cancelled.")
            break
        except Exception as e:
            logger.error("Error during scheduled MIS email ingestion: %s", e)

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Initialize PRISM database tables and optional seed
    prism_settings = get_prism_settings()
    try:
        init_prism_db()
        if prism_settings.seed_on_startup:
            seed_prism_database()
        logger.info("PRISM database initialized successfully.")
    except Exception as exc:
        logger.warning("PRISM startup init_db/seed skipped or encountered error: %s", exc)

    # 2. Startup: Launch MIS email ingestion scheduler if enabled
    scheduler_task = None
    if mis_settings.EMAIL_INGESTION_ENABLED:
        scheduler_task = asyncio.create_task(mis_email_ingestion_scheduler())

    yield

    # 3. Shutdown
    if scheduler_task and not scheduler_task.done():
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("MIS Email Ingestion scheduler cleanly shut down.")


def create_app() -> FastAPI:
    prism_settings = get_prism_settings()
    is_prod = prism_settings.environment.lower() in {"production", "prod"}

    app = FastAPI(
        title="Unified MIS & PRISM Platform API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # Allowed CORS origins combining MIS and PRISM configurations
    raw_origins = set()
    for o in (mis_settings.CORS_ORIGINS or "").split(","):
        if o.strip():
            raw_origins.add(o.strip())
    for o in prism_settings.get_cors_origins():
        if o.strip():
            raw_origins.add(o.strip())

    cors_origins = list(raw_origins) if raw_origins else ["http://localhost:5173", "http://127.0.0.1:5173"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.add_middleware(
        SecurityHeadersMiddleware,
        hsts_enabled=prism_settings.hsts_enabled,
        hsts_max_age=prism_settings.hsts_max_age,
        csp_policy=prism_settings.csp_policy,
    )

    # --------------------------------------------------------------------------
    # Root & Health Check Endpoints
    # --------------------------------------------------------------------------
    @app.get("/")
    def root():
        return {
            "name": "Unified MIS & PRISM Platform API",
            "version": "1.0.0",
            "status": "online",
            "modules": ["mis", "prism"],
        }

    @app.get("/health")
    async def health():
        """Dual database connectivity check for MIS (async) and PRISM (sync)."""
        mis_db_status = "unknown"
        prism_db_status = "unknown"

        # Check MIS DB
        try:
            async with mis_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            mis_db_status = "healthy"
        except Exception as e:
            mis_db_status = f"unreachable ({e.__class__.__name__})"

        # Check PRISM DB
        try:
            p_engine = get_prism_engine()
            with p_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            prism_db_status = "healthy"
        except Exception as e:
            prism_db_status = f"unreachable ({e.__class__.__name__})"

        overall_status = "ok" if (mis_db_status == "healthy" or prism_db_status == "healthy") else "degraded"

        return {
            "status": overall_status,
            "databases": {
                "mis": mis_db_status,
                "prism": prism_db_status,
            },
        }

    # --------------------------------------------------------------------------
    # Common Authentication API
    # --------------------------------------------------------------------------
    class UnifiedLoginRequest(BaseModel):
        email: str
        password: str
        app: Optional[str] = Field(default="mis", description="'mis' or 'prism'")

    @app.post("/api/v1/auth/login")
    async def unified_login(payload: UnifiedLoginRequest, request: Request, response: Response):
        """Unified login endpoint supporting both Starts MIS and PRISM logins."""
        target_app = (payload.app or "mis").strip().lower()

        if target_app == "prism":
            # Delegate to PRISM auth
            p_engine = get_prism_engine()
            from sqlalchemy.orm import Session
            with Session(p_engine) as db:
                fingerprint = prism_auth_service.extract_client_fingerprint(request)
                access, refresh, user_out = prism_auth_service.login(
                    db,
                    PrismLoginRequest(email=payload.email, password=payload.password),
                    client_fingerprint=fingerprint,
                )
                secure = prism_settings.environment != "development"
                response.set_cookie(
                    key="access_token",
                    value=access,
                    httponly=True,
                    secure=secure,
                    samesite="lax",
                    max_age=prism_settings.access_token_expire_minutes * 60,
                    path="/",
                )
                response.set_cookie(
                    key="refresh_token",
                    value=refresh,
                    httponly=True,
                    secure=secure,
                    samesite="lax",
                    max_age=prism_settings.refresh_token_expire_minutes * 60,
                    path="/",
                )
                return {
                    "app": "prism",
                    "user": user_out,
                    "access_token": access if prism_settings.environment == "development" else None,
                    "message": "PRISM sign-in successful",
                }

        # Otherwise authenticate against Starts MIS
        email_clean = payload.email.strip().lower()
        password_clean = payload.password.strip()

        from mis.db.session import AsyncSessionLocal
        from sqlalchemy import func
        user = None
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(MisUser)
                    .options(selectinload(MisUser.role))
                    .where(func.lower(func.trim(MisUser.email)) == email_clean, MisUser.deleted_at.is_(None))
                )
                user = result.scalar_one_or_none()
        except Exception as exc:
            logger.warning("MIS DB query failed: %s", exc)

        if user and mis_verify_password(password_clean, user.password_hash):
            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

            token = mis_create_access_token(user_id=user.id, email=user.email, role_code=user.role.code)
            is_secure = mis_settings.AUTH_COOKIE_SECURE or request.url.scheme == "https"
            response.set_cookie(
                key=mis_settings.AUTH_COOKIE_NAME,
                value=token,
                max_age=mis_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                httponly=True,
                secure=is_secure,
                samesite=mis_settings.AUTH_COOKIE_SAMESITE,
                path="/",
            )
            from mis.api.v1.endpoints.auth import _frontend_role
            role_code = user.role.code if user.role else "RECRUITER"
            frontend_role = _frontend_role(role_code)
            return {
                "app": "mis",
                "role": frontend_role,
                "role_code": role_code,
                "name": user.full_name,
                "email": user.email,
                "access_token": token,
                "message": "Starts MIS sign-in successful",
            }

        # If not found in MIS, check if credentials belong to PRISM (fallback)
        try:
            p_engine = get_prism_engine()
            from sqlalchemy.orm import Session
            with Session(p_engine) as db:
                fingerprint = prism_auth_service.extract_client_fingerprint(request)
                access, refresh, user_out = prism_auth_service.login(
                    db,
                    PrismLoginRequest(email=payload.email, password=payload.password),
                    client_fingerprint=fingerprint,
                )
                secure = prism_settings.environment != "development"
                response.set_cookie(
                    key="access_token",
                    value=access,
                    httponly=True,
                    secure=secure,
                    samesite="lax",
                    max_age=prism_settings.access_token_expire_minutes * 60,
                    path="/",
                )
                response.set_cookie(
                    key="refresh_token",
                    value=refresh,
                    httponly=True,
                    secure=secure,
                    samesite="lax",
                    max_age=prism_settings.refresh_token_expire_minutes * 60,
                    path="/",
                )
                return {
                    "app": "prism",
                    "user": user_out,
                    "access_token": access if prism_settings.environment == "development" else None,
                    "message": "PRISM sign-in successful",
                }
        except Exception:
            pass

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    @app.post("/api/v1/auth/logout")
    def unified_logout(request: Request, response: Response):
        """Unified logout clearing all MIS and PRISM session cookies."""
        secure = prism_settings.environment != "development"
        response.delete_cookie(key=mis_settings.AUTH_COOKIE_NAME, path="/")
        response.delete_cookie(key="access_token", path="/", secure=secure, samesite="lax")
        response.delete_cookie(key="refresh_token", path="/", secure=secure, samesite="lax")
        return {"status": "ok", "message": "Signed out from all workspaces"}

    @app.post("/api/v1/auth/refresh")
    async def unified_refresh(request: Request, response: Response, refresh_token: Optional[str] = Cookie(None)):
        """Unified token refresh endpoint supporting PRISM session refresh."""
        token_val = refresh_token
        if not token_val:
            try:
                body = await request.json()
                token_val = body.get("refresh_token")
            except Exception:
                pass
        if not token_val:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")
        p_engine = get_prism_engine()
        from sqlalchemy.orm import Session
        with Session(p_engine) as db:
            fingerprint = prism_auth_service.extract_client_fingerprint(request)
            access, new_refresh, user_out = prism_auth_service.refresh(db, token_val, client_fingerprint=fingerprint)
            secure = prism_settings.environment != "development"
            response.set_cookie(key="access_token", value=access, httponly=True, secure=secure, samesite="lax", max_age=prism_settings.access_token_expire_minutes * 60)
            response.set_cookie(key="refresh_token", value=new_refresh, httponly=True, secure=secure, samesite="lax", max_age=prism_settings.refresh_token_expire_minutes * 60)
            return {"user": user_out, "access_token": access if prism_settings.environment == "development" else None}

    # --------------------------------------------------------------------------
    # Mount Namespaced Routers: /api/v1/mis/* and /api/v1/prism/*
    # --------------------------------------------------------------------------
    app.include_router(mis_router, prefix="/api/v1/mis", tags=["MIS Module"])

    prism_v1 = FastAPI()
    # PRISM Routers under /api/v1/prism
    app.include_router(prism_auth_router, prefix="/api/v1/prism/auth", tags=["PRISM Auth"])
    app.include_router(prism_dashboard_router, prefix="/api/v1/prism/dashboard", tags=["PRISM Dashboard"])
    app.include_router(prism_organization_router, prefix="/api/v1/prism", tags=["PRISM Organization"])
    app.include_router(prism_candidates_router, prefix="/api/v1/prism", tags=["PRISM Candidates"])
    app.include_router(prism_coordinators_router, prefix="/api/v1/prism/coordinators", tags=["PRISM Coordinators"])
    app.include_router(prism_hours_router, prefix="/api/v1/prism/hours-data", tags=["PRISM Hours"])
    app.include_router(prism_hours_benchmarks_router, prefix="/api/v1/prism/hours-benchmarks", tags=["PRISM Hours Benchmarks"])
    app.include_router(prism_project_end_router, prefix="/api/v1/prism/project-end", tags=["PRISM Project End"])
    app.include_router(prism_cycles_router, prefix="/api/v1/prism/cycles", tags=["PRISM Cycles"])
    app.include_router(prism_incentives_router, prefix="/api/v1/prism", tags=["PRISM Incentives"])
    app.include_router(prism_audit_router, prefix="/api/v1/prism/audit", tags=["PRISM Audit"])
    app.include_router(prism_vlookup_router, prefix="/api/v1/prism/vlookup", tags=["PRISM VLookup"])
    app.include_router(prism_reports_router, prefix="/api/v1/prism", tags=["PRISM Reports"])
    app.include_router(prism_special_incentive_router, prefix="/api/v1/prism/special-incentive", tags=["PRISM Special Incentive"])

    # --------------------------------------------------------------------------
    # Backward Compatibility: Mount Existing Endpoints at /api/v1/*
    # --------------------------------------------------------------------------
    app.include_router(mis_router, prefix="/api/v1", tags=["MIS Endpoints"])
    app.include_router(prism_candidates_router, prefix="/api/v1", tags=["PRISM Candidates"])
    app.include_router(prism_coordinators_router, prefix="/api/v1/coordinators", tags=["PRISM Coordinators"])
    app.include_router(prism_hours_router, prefix="/api/v1/hours-data", tags=["PRISM Hours"])
    app.include_router(prism_hours_benchmarks_router, prefix="/api/v1/hours-benchmarks", tags=["PRISM Hours Benchmarks"])
    app.include_router(prism_project_end_router, prefix="/api/v1/project-end", tags=["PRISM Project End"])
    app.include_router(prism_cycles_router, prefix="/api/v1/cycles", tags=["PRISM Cycles"])
    app.include_router(prism_vlookup_router, prefix="/api/v1/vlookup", tags=["PRISM VLookup"])
    app.include_router(prism_special_incentive_router, prefix="/api/v1/special-incentive", tags=["PRISM Special Incentive"])
    app.include_router(prism_dashboard_router, prefix="/api/v1/dashboard", tags=["PRISM Dashboard Compat"])
    app.include_router(prism_audit_router, prefix="/api/v1/audit", tags=["PRISM Audit Compat"])
    app.include_router(prism_reports_router, prefix="/api/v1", tags=["PRISM Reports Compat"])

    # --------------------------------------------------------------------------
    # Exception Handlers
    # --------------------------------------------------------------------------
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
