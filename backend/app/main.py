"""FastAPI application entrypoint (Phase 1: ingestion + read APIs)."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.init_db import init_db
from app.syslog.listener import SyslogListenerManager
from app.syslog.pipeline import IngestionPipeline

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, start pipeline + listeners. Shutdown: stop cleanly."""
    setup_logging(settings.log_level)
    logger.info("Starting %s (%s)", settings.app_name, settings.environment)

    init_db()

    pipeline = IngestionPipeline(
        maxsize=settings.syslog_queue_maxsize,
        workers=settings.syslog_worker_count,
    )
    listeners = SyslogListenerManager(on_message=pipeline.submit)
    app.state.pipeline = pipeline
    app.state.listeners = listeners
    app.state.started_at = datetime.now(timezone.utc)
    app.state.uptime_base = time.monotonic()

    await pipeline.start()
    if listeners.enabled:
        await listeners.start_all()
    else:
        logger.info("Syslog listeners disabled by configuration")

    yield

    await listeners.stop_all()
    await pipeline.stop()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Application factory (kept for tests and future ASGI mounting)."""
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Phase 1 — syslog ingestion, normalization and read APIs. "
            "Detection, correlation, RCA, alerts and topology arrive in later phases."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/api/docs",
            "health": f"{settings.api_v1_prefix}/health",
        }

    return application


app = create_app()
