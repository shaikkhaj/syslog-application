"""Shared DB aggregations for health scoring, RCA and topology (Phase 5).

These helpers used to live privately in ``api/v1/topology.py``; they are
promoted here so the topology, RCA and network-health endpoints all derive
their view from the exact same query results (single implementation).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.correlation.engine import ACTIVE_STATUSES
from app.models.models import Alert, Incident, SyslogEvent


def open_alerts_by_device(db: Session) -> dict[int, dict]:
    """Open (non-resolved) alerts grouped by device id."""
    alerts = (
        db.execute(select(Alert).where(Alert.status != "resolved")).scalars().all()
    )
    grouped: dict[int, dict] = {}
    for alert in alerts:
        if alert.device_id is None:
            continue
        entry = grouped.setdefault(
            alert.device_id, {"count": 0, "severities": [], "interfaces": set()}
        )
        entry["count"] += 1
        entry["severities"].append(alert.severity)
        interface = (alert.context or {}).get("interface")
        if interface:
            entry["interfaces"].add(str(interface))
    return grouped


def active_incidents_by_device(db: Session) -> dict[int, list[str]]:
    """Active incident severities grouped by affected device id."""
    incidents = (
        db.execute(select(Incident).where(Incident.status.in_(ACTIVE_STATUSES)))
        .scalars()
        .all()
    )
    grouped: dict[int, list[str]] = {}
    for incident in incidents:
        device_ids = {incident.device_id}
        for entry in incident.affected_devices or []:
            if entry.get("device_id"):
                device_ids.add(entry["device_id"])
        for device_id in device_ids:
            if device_id:
                grouped.setdefault(device_id, []).append(incident.severity)
    return grouped


def recent_event_counts(db: Session, since: datetime) -> dict[int, int]:
    """Syslog events per device with ``received_at >= since`` (0 rows omitted)."""
    rows = db.execute(
        select(SyslogEvent.device_id, func.count().label("event_count"))
        .where(SyslogEvent.device_id.is_not(None), SyslogEvent.received_at >= since)
        .group_by(SyslogEvent.device_id)
    ).all()
    return {device_id: int(count) for device_id, count in rows if device_id is not None}
