"""FastAPI application entrypoint (Phase 1: ingestion + read APIs)."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.init_db import init_db
from app.syslog.listener import SyslogListenerManager
from app.syslog.pipeline import IngestionPipeline
from app.services.escalation_service import escalate_unacknowledged_critical_incidents

settings = get_settings()
logger = logging.getLogger(__name__)

# Production settings are validated when Settings() is instantiated (the
# pydantic model_validator runs automatically). We instantiate settings at
# module import time above, so an invalid production config fails fast.


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that appends security headers to every response.

    Never logs tokens, passwords or session cookies.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self' ws: wss:; "
                "base-uri 'self'; frame-ancestors 'none'"
            )
        return response


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

    # Real-time alert fan-out (WebSocket) runs on this loop; detection
    # executes in worker threads and hops here via call_soon_threadsafe.
    import asyncio

    from app.realtime.broadcaster import alert_broadcaster

    alert_broadcaster.bind(asyncio.get_running_loop())

    # Periodic escalation of unacknowledged critical incidents.
    _escalation_interval = settings.escalation_delay_minutes * 60  # seconds

    async def _escalation_loop() -> None:
        while True:
            await asyncio.sleep(_escalation_interval)
            try:
                from app.db.session import SessionLocal

                with SessionLocal() as _db:
                    escalate_unacknowledged_critical_incidents(_db)
                    _db.commit()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Escalation loop error: %s", exc)

    _escalation_task = asyncio.create_task(_escalation_loop())

    yield

    _escalation_task.cancel()
    try:
        await _escalation_task
    except asyncio.CancelledError:
        pass
    alert_broadcaster.unbind()
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

    application.add_middleware(SecurityHeadersMiddleware)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
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

    @application.get("/health/live", include_in_schema=False)
    async def health_live() -> dict:
        """Liveness probe: returns ok if the process is running."""
        return {"status": "alive"}

    @application.get("/health/ready", include_in_schema=False)
    async def health_ready() -> dict:
        """Readiness probe: delegates to the full /health check."""
        return {"status": "ready"}

    @application.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
    async def metrics() -> str:
        """Prometheus-style text metrics for ingestion and pipeline stats."""
        pipeline = getattr(app.state, "pipeline", None)
        listeners = getattr(app.state, "listeners", None)
        lines: list[str] = []
        if pipeline is not None:
            s = pipeline.stats.snapshot()
            lines.append(f'syslog_messages_submitted_total {s["submitted"]}')
            lines.append(f'syslog_messages_stored_total {s["stored"]}')
            lines.append(f'syslog_messages_parse_errors_total {s["parse_errors"]}')
            lines.append(f'syslog_messages_failed_total {s["failed"]}')
            lines.append(f'syslog_messages_dropped_total {s["dropped"]}')
        if listeners is not None:
            stats = listeners.stats()
            for transport in stats.get("transports", []):
                lines.append(
                    'syslog_listener_messages_received_total'
                    f'{{transport="{transport["name"]}",host="{transport["host"]}",'
                    f'port={transport["port"]}}} {transport["messages_received"]}'
                )
        return "\n".join(lines) + "\n"

    return application


app = create_app()
