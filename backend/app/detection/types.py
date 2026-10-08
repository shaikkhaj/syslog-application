"""Shared types for the detection engine (Phase 2).

``EventType`` is the canonical classification taxonomy used by:

* the ``event_types`` catalog and ``syslog_events.event_type_code`` (ingestion), and
* alerts raised by the detection rules.

``AlertSeverity`` is the alerting scale (independent from raw syslog severity).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    """Canonical event classification codes."""

    INTERFACE_DOWN = "INTERFACE_DOWN"
    INTERFACE_UP = "INTERFACE_UP"
    LINK_FLAP = "LINK_FLAP"
    BGP_DOWN = "BGP_DOWN"
    BGP_UP = "BGP_UP"
    OSPF_NEIGHBOR_DOWN = "OSPF_NEIGHBOR_DOWN"
    OSPF_NEIGHBOR_UP = "OSPF_NEIGHBOR_UP"
    AUTH_FAILURE = "AUTH_FAILURE"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    CPU_HIGH = "CPU_HIGH"
    MEMORY_HIGH = "MEMORY_HIGH"
    ROUTE_CHANGE = "ROUTE_CHANGE"
    DEVICE_UNREACHABLE = "DEVICE_UNREACHABLE"
    # Retained Phase 1 classifications without dedicated alerting rules:
    INTERFACE_ERROR = "INTERFACE_ERROR"
    SYSTEM_RESTART = "SYSTEM_RESTART"
    OTHER = "OTHER"

    @classmethod
    def codes(cls) -> list[str]:
        return [member.value for member in cls]


class AlertSeverity(str, Enum):
    """Alert severity scale (ordered: INFO < LOW < MEDIUM < HIGH < CRITICAL)."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @classmethod
    def order(cls, severity: "AlertSeverity | str") -> int:
        values = [member.value for member in cls]
        value = severity.value if isinstance(severity, AlertSeverity) else severity
        return values.index(value)


class AlertStatus(str, Enum):
    """Alert lifecycle states (Phase 3 correlation will extend this)."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class DetectionResult:
    """A finding produced by one detection rule for one event."""

    event_type: EventType
    severity: AlertSeverity
    title: str
    dedupe_key: str
    message: str = ""
    context: dict = field(default_factory=dict)
    rule_name: str = ""
