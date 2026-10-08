"""Authentication-failure detection with configurable threshold/window.

Counts AUTH_FAILURE events per (device, remote attacker IP) inside the
configured window. The attacker IP is extracted from the message body with
vendor-aware patterns (Cisco ``[Source: 10.0.0.99]``, Linux sshd
``from 203.0.113.77``, FortiGate ``srcip=...``) — the syslog source IP only
identifies the device that forwarded the message.

Findings below the threshold stay silent; the crossing event raises a MEDIUM
alert which escalates to HIGH once failures reach three times the threshold.
Threshold and window are environment-configurable.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.detection.config import DetectionConfig
from app.detection.rules.base import DetectionRule
from app.detection.types import AlertSeverity, DetectionResult, EventType
from app.models.models import SyslogEvent

ESCALATION_MULTIPLIER = 3

_IPV4 = r"\d{1,3}(?:\.\d{1,3}){3}"
_ATTACKER_PATTERNS = [
    re.compile(r"\[Source:\s*(" + _IPV4 + r")\]", re.IGNORECASE),  # Cisco
    re.compile(r"\bsrcip=(" + _IPV4 + r")", re.IGNORECASE),  # FortiGate
    re.compile(r"\bfrom\s+(" + _IPV4 + r")\b", re.IGNORECASE),  # sshd
    re.compile(_IPV4),  # generic fallback: first IPv4 in the message
]


def _attacker_ip(message: str) -> str | None:
    for pattern in _ATTACKER_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    return None


class AuthFailureRule(DetectionRule):
    name = "auth_failure_threshold"
    event_types = frozenset({EventType.AUTH_FAILURE})

    def evaluate(self, event, db: Session, config: DetectionConfig):
        attacker = _attacker_ip(event.message)
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=config.auth_failure_window_seconds
        )
        filters = [
            SyslogEvent.device_id == event.device_id,
            SyslogEvent.event_type_code == EventType.AUTH_FAILURE.value,
            SyslogEvent.received_at >= cutoff,
        ]
        if attacker:
            filters.append(SyslogEvent.message.contains(attacker))
        failures = db.execute(
            select(func.count()).select_from(SyslogEvent).where(*filters)
        ).scalar_one()

        if failures < config.auth_failure_threshold:
            return  # single/limited failures: below the alerting threshold

        severity = (
            AlertSeverity.HIGH
            if failures >= config.auth_failure_threshold * ESCALATION_MULTIPLIER
            else AlertSeverity.MEDIUM
        )
        host = self._host(event)
        actor = attacker or event.source_ip
        yield DetectionResult(
            event_type=EventType.AUTH_FAILURE,
            severity=severity,
            title=(
                f"Repeated authentication failures from {actor} on {host} "
                f"({failures} in {config.auth_failure_window_seconds}s)"
            ),
            message=event.message,
            dedupe_key=f"AUTH_FAILURE:{self._device_part(event)}:{actor}",
            context={
                "source_ip": attacker,
                "device_source_ip": event.source_ip,
                "failures_in_window": failures,
                "threshold": config.auth_failure_threshold,
                "window_seconds": config.auth_failure_window_seconds,
                "vendor": event.vendor,
            },
            rule_name=self.name,
        )
