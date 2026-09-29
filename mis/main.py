import sys
from pathlib import Path

# Ensure the root directory is in the Python path when running this file directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from mis.api.v1.router import api_router
from mis.core.config import settings
from mis.middleware.cors import add_cors
from mis.middleware.security import SecurityMiddleware
from mis.services.email_ingestion.pipeline import run_email_ingestion_pipeline


async def email_ingestion_scheduler():
    """Background task that runs the email ingestion pipeline at configured intervals."""
    if not settings.EMAIL_INGESTION_ENABLED:
        logger.info("Email Ingestion background scheduler is disabled.")
        return

    interval_minutes = max(settings.EMAIL_INGESTION_INTERVAL_MINUTES, 1)
    interval_seconds = interval_minutes * 60
    retry_seconds = 15 * 60
    is_retry = False

    logger.info(
        f"Email Ingestion background scheduler started (running every {interval_minutes} minute(s))."
    )

    while True:
        processed_emails = False
        try:
            logger.info("Triggering scheduled Email Ingestion Pipeline...")
            processed_emails = await asyncio.to_thread(run_email_ingestion_pipeline)
        except asyncio.CancelledError:
            logger.info("Email Ingestion background scheduler task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error during scheduled email ingestion: {e}")

        try:
            if not processed_emails and not is_retry:
                logger.info("No emails processed. Scheduling a one-time retry in 15 minutes.")
                await asyncio.sleep(retry_seconds)
                is_retry = True
            else:
                sleep_time = interval_seconds - retry_seconds if is_retry else interval_seconds
                logger.info(f"Pipeline complete. Sleeping for {sleep_time // 60} minute(s) until next cycle.")
                await asyncio.sleep(sleep_time)
                is_retry = False
        except asyncio.CancelledError:
            logger.info("Email Ingestion background scheduler sleep interrupted for shutdown.")
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler_task = None
    if settings.EMAIL_INGESTION_ENABLED:
        scheduler_task = asyncio.create_task(email_ingestion_scheduler())

    yield

    # Shutdown
    if scheduler_task and not scheduler_task.done():
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("Email Ingestion scheduler shut down cleanly.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
    lifespan=lifespan,
)

add_cors(app)
app.add_middleware(SecurityMiddleware)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
