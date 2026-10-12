"""Shared types for the correlation engine (Phase 3)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from app.detection.types import AlertSeverity, EventType


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize datetimes for comparisons.

    SQLite returns naive datetimes (treated as UTC); PostgreSQL returns
    offset-aware ones. All correlation logic compares through this helper.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class IncidentStatus(str, Enum):
    """Incident lifecycle states."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

    @classmethod
    def active(cls) -> list[str]:
        """Statuses that still accept correlated alerts."""
        return [cls.OPEN.value, cls.INVESTIGATING.value, cls.ACKNOWLEDGED.value]


class IncidentSeverity(str, Enum):
    """Incident severity scale (no INFO — alert INFO maps to LOW)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @classmethod
    def order(cls, severity: "IncidentSeverity | str") -> int:
        values = [member.value for member in cls]
        value = severity.value if isinstance(severity, IncidentSeverity) else severity
        return values.index(value) if value in values else 0


# Alert severity → incident severity (INFO is informational only).
_ALERT_TO_INCIDENT_SEVERITY: dict[str, IncidentSeverity] = {
    AlertSeverity.INFO.value: IncidentSeverity.LOW,
    AlertSeverity.LOW.value: IncidentSeverity.LOW,
    AlertSeverity.MEDIUM.value: IncidentSeverity.MEDIUM,
    AlertSeverity.HIGH.value: IncidentSeverity.HIGH,
    AlertSeverity.CRITICAL.value: IncidentSeverity.CRITICAL,
}

SEVERITY_POINTS: dict[str, int] = {
    IncidentSeverity.LOW.value: 1,
    IncidentSeverity.MEDIUM.value: 2,
    IncidentSeverity.HIGH.value: 3,
    IncidentSeverity.CRITICAL.value: 4,
}


def incident_severity_from_alert(alert_severity: str) -> IncidentSeverity:
    return _ALERT_TO_INCIDENT_SEVERITY.get(alert_severity, IncidentSeverity.LOW)


# Incident states that signal the network recovered (timeline markers).
RECOVERY_EVENT_TYPES = {
    EventType.INTERFACE_UP.value,
    EventType.BGP_UP.value,
    EventType.OSPF_NEIGHBOR_UP.value,
}

# Primary failure types vs. consequences used by the causal-chain rule.
PRIMARY_FAILURE_TYPES = {
    EventType.INTERFACE_DOWN.value,
    EventType.LINK_FLAP.value,
    EventType.BGP_DOWN.value,
    EventType.OSPF_NEIGHBOR_DOWN.value,
    EventType.DEVICE_UNREACHABLE.value,
    EventType.VPN_DISCONNECT.value,
}
CONSEQUENCE_TYPES = {
    EventType.ROUTE_CHANGE.value,
    EventType.DEVICE_UNREACHABLE.value,
    EventType.LINK_FLAP.value,
}
