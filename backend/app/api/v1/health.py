"""Health endpoint: database, Redis and syslog listener status."""

from __future__ import annotations

import logging
import time

import redis as redis_lib
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.realtime.broadcaster import alert_broadcaster
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])
settings = get_settings()


def _check_database(db: Session) -> dict:
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception:
        logger.exception("Health check: database unavailable")
        return {"status": "error", "detail": "database connection failed"}


def _check_redis() -> dict:
    client = redis_lib.Redis.from_url(
        settings.redis_url, socket_connect_timeout=1.5, socket_timeout=1.5
    )
    try:
        client.ping()
        return {"status": "ok"}
    except Exception:
        logger.warning("Health check: redis unavailable at %s", settings.redis_url)
        return {"status": "error", "detail": "redis unreachable"}
    finally:
        try:
            client.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass


@router.get("/health", response_model=HealthResponse, summary="System health")
def health(request: Request, db: Session = Depends(get_db)) -> HealthResponse:
    checks: dict = {
        "database": _check_database(db),
        "redis": _check_redis(),
    }

    manager = getattr(request.app.state, "listeners", None)
    pipeline = getattr(request.app.state, "pipeline", None)
    if manager is None:
        checks["syslog"] = {"status": "stopped"}
    else:
        listener_stats = manager.stats()
        checks["syslog"] = {
            "status": listener_stats["status"],
            "listeners": listener_stats["transports"],
            "errors": listener_stats["errors"],
            "pipeline": pipeline.stats.snapshot() if pipeline else None,
        }

    # Detection engine (Phase 2)
    from app.detection.engine import get_detection_engine

    engine = get_detection_engine()
    checks["detection"] = {
        "status": "ok" if engine.config.enabled else "disabled",
        "rules": len(engine.rules),
        "websocket_subscribers": alert_broadcaster.subscriber_count,
        **engine.snapshot(),
    }

    # Correlation engine (Phase 3)
    from app.correlation import get_correlation_engine

    correlation = get_correlation_engine()
    checks["correlation"] = {
        "status": "ok" if correlation.config.enabled else "disabled",
        "rules": len(correlation.rules),
        "window_seconds": correlation.config.time_window_seconds,
        **correlation.snapshot_stats(),
    }

    if checks["database"]["status"] != "ok":
        overall = "error"
    elif all(check["status"] in ("ok", "disabled") for check in checks.values()):
        overall = "ok"
    else:
        overall = "degraded"

    uptime_base = getattr(request.app.state, "uptime_base", None)
    uptime = (time.monotonic() - uptime_base) if uptime_base else 0.0
    return HealthResponse(
        status=overall,
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=round(uptime, 1),
        checks=checks,
    )
