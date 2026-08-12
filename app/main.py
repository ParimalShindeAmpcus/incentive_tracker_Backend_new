"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Root health (existing contract)
    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(health_router, prefix=f"{prefix}/health", tags=["health"])

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

    return app


app = create_app()
