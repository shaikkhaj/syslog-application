"""System-level detection: configuration changes and unreachability.

Vendor-aware actor extraction:

* Cisco — ``Configured from console by admin on vty0``
* FortiGate — ``user="admin"`` / ``Configuration is changed``
* Linux — ``changed by user deploy`` / ``operator root``
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.detection.config import DetectionConfig
from app.detection.rules.base import DetectionRule
from app.detection.types import AlertSeverity, DetectionResult, EventType
from app.models.models import SyslogEvent

_IPV4 = r"\d{1,3}(?:\.\d{1,3}){3}"

_ACTOR_EXTRACTORS = [
    re.compile(r"by\s+(\S+)\s+on\s+vty", re.IGNORECASE),  # Cisco console/vty
    re.compile(r'user="([^"]+)"', re.IGNORECASE),  # FortiGate admin
    re.compile(r"by user\s+(\S+)", re.IGNORECASE),  # Linux / custom agents
    re.compile(r"operator\s+(\S+)", re.IGNORECASE),
]
_TARGET_EXTRACTORS = [re.compile(_IPV4)]


def _first(patterns: list[re.Pattern], message: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(message)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    return None


class ConfigChangeRule(DetectionRule):
    name = "config_change"
    event_types = frozenset({EventType.CONFIG_CHANGE})

    def evaluate(self, event: SyslogEvent, db: Session, config: DetectionConfig):
        actor = _first(_ACTOR_EXTRACTORS, event.message)
        host = self._host(event)
        yield DetectionResult(
            event_type=EventType.CONFIG_CHANGE,
            severity=AlertSeverity.LOW,
            title=(
                f"Configuration changed on {host} by {actor}"
                if actor
                else f"Configuration changed on {host}"
            ),
            message=event.message,
            dedupe_key=f"CONFIG_CHANGE:{self._device_part(event)}",
            context={"actor": actor, "vendor": event.vendor},
            rule_name=self.name,
        )


class DeviceUnreachableRule(DetectionRule):
    name = "device_unreachable"
    event_types = frozenset({EventType.DEVICE_UNREACHABLE})

    def evaluate(self, event: SyslogEvent, db: Session, config: DetectionConfig):
        target = _first(_TARGET_EXTRACTORS, event.message)
        host = self._host(event)
        yield DetectionResult(
            event_type=EventType.DEVICE_UNREACHABLE,
            severity=AlertSeverity.CRITICAL,
            title=(
                f"Unreachable target {target} reported by {host}"
                if target
                else f"Unreachability reported by {host}"
            ),
            message=event.message,
            dedupe_key=(
                f"DEVICE_UNREACHABLE:{self._device_part(event)}:{target or 'unknown'}"
            ),
            context={"target": target, "vendor": event.vendor},
            rule_name=self.name,
        )
