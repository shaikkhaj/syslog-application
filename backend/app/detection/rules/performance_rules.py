"""Device performance detection: CPU_HIGH / MEMORY_HIGH thresholds.

Extracts the utilization percentage from the normalized message
(``cpu_utilization=93%``, ``memory_usage=92%``, ``CPU usage is 96%`` …) and
compares it against the *configured* thresholds. Values below the configured
threshold are suppressed even when the catalog already classified the event
as high utilization — nothing here is hardcoded.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.detection.config import DetectionConfig
from app.detection.rules.base import DetectionRule
from app.detection.types import AlertSeverity, DetectionResult, EventType
from app.models.models import SyslogEvent

_PERCENT_PATTERNS = {
    "cpu": [
        re.compile(r"cpu[_\s]?(?:utilization|usage)[^\d%]{0,12}(\d{1,3})\s?%", re.I),
        re.compile(r"\bcpu[^\d%]{0,12}(\d{1,3})\s?%", re.I),
    ],
    "memory": [
        re.compile(r"memory[_\s]?(?:usage|utilization)[^\d%]{0,12}(\d{1,3})\s?%", re.I),
        re.compile(r"\bmemory[^\d%]{0,12}(\d{1,3})\s?%", re.I),
    ],
}


def _percent(kind: str, message: str) -> int | None:
    for pattern in _PERCENT_PATTERNS[kind]:
        match = pattern.search(message)
        if match:
            value = int(match.group(1))
            if 0 <= value <= 100:
                return value
    return None


class PerformanceRule(DetectionRule):
    name = "performance_threshold"
    event_types = frozenset({EventType.CPU_HIGH, EventType.MEMORY_HIGH})

    def evaluate(self, event: SyslogEvent, db: Session, config: DetectionConfig):
        is_cpu = event.event_type_code == EventType.CPU_HIGH.value
        kind = "cpu" if is_cpu else "memory"
        value = _percent(kind, event.message)
        threshold = (
            config.cpu_high_threshold_percent
            if is_cpu
            else config.memory_high_threshold_percent
        )
        if value is not None and value < threshold:
            return  # below the configured threshold — suppress

        host = self._host(event)
        label = "CPU" if is_cpu else "Memory"
        yield DetectionResult(
            event_type=EventType.CPU_HIGH if is_cpu else EventType.MEMORY_HIGH,
            severity=AlertSeverity.MEDIUM,
            title=(
                f"High {label.lower()} on {host}: {value}%"
                if value is not None
                else f"High {label.lower()} usage reported by {host}"
            ),
            message=event.message,
            dedupe_key=(
                f"{'CPU_HIGH' if is_cpu else 'MEMORY_HIGH'}:"
                f"{self._device_part(event)}"
            ),
            context={
                "utilization_percent": value,
                "threshold_percent": threshold,
                "vendor": event.vendor,
            },
            rule_name=self.name,
        )
