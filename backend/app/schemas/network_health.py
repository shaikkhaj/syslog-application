"""Response schemas for RCA reports and network health scores (Phase 5)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RcaCandidateOut(BaseModel):
    """Phase 3 failure-mode candidate (reused, not re-derived)."""

    rank: int
    code: str
    title: str
    description: str = ""
    confidence: float
    # Phase 3 stores structured evidence items ({"event_type", "count"}).
    evidence: list[Any] = []


class RcaDeviceOut(BaseModel):
    """A probable root-cause device with audit trail."""

    rank: int
    device_id: int
    hostname: str | None = None
    ip_address: str | None = None
    score: float
    reasons: list[str] = []


class RcaUpstreamOut(BaseModel):
    """Topology-derived upstream dependency of the primary suspect."""

    device_id: int
    hops: int
    device_type: str = "unknown"
    hostname: str | None = None
    ip_address: str | None = None
    reason: str


class RcaReportResponse(BaseModel):
    incident_id: int
    title: str
    status: str
    severity: str
    confidence: float | None = None
    summary: str
    candidates: list[RcaCandidateOut] = []
    device_ranking: list[RcaDeviceOut] = []
    upstream_dependencies: list[RcaUpstreamOut] = []
    primary_device_id: int | None = None


class DeviceHealthOut(BaseModel):
    """Health score (0–100) and signal breakdown for one device."""

    device_id: int
    hostname: str | None = None
    ip_address: str
    device_type: str = "router"
    status: str
    score: float
    band: str  # healthy | degraded | critical
    open_alerts: int = 0
    max_alert_severity: str | None = None
    active_incidents: int = 0
    recent_events: int = 0
    breakdown: dict[str, float] = {}


class NetworkHealthResponse(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    band: str  # healthy | degraded | critical
    window_minutes: int
    device_count: int
    counts: dict[str, int]  # healthy | degraded | critical
    items: list[DeviceHealthOut] = []  # worst first, capped by ?limit
