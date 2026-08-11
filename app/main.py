from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.base import Base
from app.db.init_db import init_db
from app.db.session import SessionLocal, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_startup:
        db = SessionLocal()
        try:
            init_db(db)
        finally:
            db.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Incentive Tracker API",
        version="1.0.0",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health")
    def health():
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
