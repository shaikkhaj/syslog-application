"""Response schema for the health endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "error"
    app: str
    version: str
    environment: str
    uptime_seconds: float
    checks: dict[str, Any]
