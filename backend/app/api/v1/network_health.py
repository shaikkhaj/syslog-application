"""Network health scores: per device + overall (Phase 5).

All scores are derived at query time from existing tables (open alerts,
active incidents, recent syslog events, device status) — nothing is stored,
mirroring the Phase 4 topology-highlighting approach.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.detection.types import AlertSeverity
from app.health.queries import (
    active_incidents_by_device,
    open_alerts_by_device,
    recent_event_counts,
)
from app.health.scoring import (
    DeviceSignals,
    HealthConfig,
    compute_device_health,
    compute_overall_health,
)
from app.models.models import Device
from app.schemas.network_health import DeviceHealthOut, NetworkHealthResponse

router = APIRouter(tags=["network-health"])

_SEVERITY_ORDER = [severity.value for severity in AlertSeverity]


def _max_severity(severities: list[str | None]) -> str | None:
    ranked = [s for s in severities if s in _SEVERITY_ORDER]
    if not ranked:
        return None
    return max(ranked, key=lambda value: _SEVERITY_ORDER.index(value))


@router.get(
    "/network-health",
    response_model=NetworkHealthResponse,
    summary="Health scores per device and overall",
)
def get_network_health(
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    device_id: Optional[int] = Query(None, ge=1),
) -> NetworkHealthResponse:
    config = HealthConfig()
    devices = list(db.execute(select(Device)).scalars().all())
    alerts = open_alerts_by_device(db)
    incidents = active_incidents_by_device(db)
    since = datetime.now(timezone.utc) - timedelta(minutes=config.window_minutes)
    events = recent_event_counts(db, since)

    items: list[DeviceHealthOut] = []
    for device in devices:
        alert_info = alerts.get(
            device.id, {"count": 0, "severities": [], "interfaces": set()}
        )
        incident_severities = incidents.get(device.id, [])
        signals = DeviceSignals(
            device_id=device.id,
            status=device.status,
            alert_severities=list(alert_info["severities"]),
            incident_severities=incident_severities,
            recent_event_count=events.get(device.id, 0),
        )
        health = compute_device_health(signals, config)
        items.append(
            DeviceHealthOut(
                device_id=device.id,
                hostname=device.hostname,
                ip_address=device.ip_address,
                device_type=device.device_type or "router",
                status=device.status,
                score=health["score"],
                band=health["band"],
                open_alerts=alert_info["count"],
                max_alert_severity=_max_severity(alert_info["severities"]),
                active_incidents=len(incident_severities),
                recent_events=signals.recent_event_count,
                breakdown=health["breakdown"],
            )
        )

    overall = compute_overall_health([item.score for item in items], config)
    items.sort(key=lambda item: (item.score, item.device_id))  # worst first
    if device_id is not None:
        items = [item for item in items if item.device_id == device_id]

    return NetworkHealthResponse(
        overall_score=overall["score"],
        band=overall["band"],
        window_minutes=config.window_minutes,
        device_count=len(devices),
        counts=overall["counts"],
        items=items[:limit],
    )
