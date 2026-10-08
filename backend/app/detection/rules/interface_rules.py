"""Interface state and link-flap detection (all vendors).

* :class:`InterfaceStateRule` — raises INTERFACE_DOWN / INTERFACE_UP alerts.
* :class:`LinkFlapRule` — counts DOWN/UP transitions for one interface inside
  a configurable window and raises a single LINK_FLAP alert when the
  configurable threshold is crossed (further transitions coalesce into the
  open alert instead of creating duplicates).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.detection.config import DetectionConfig
from app.detection.rules.base import DetectionRule
from app.detection.types import AlertSeverity, DetectionResult, EventType
from app.models.models import SyslogEvent


class InterfaceStateRule(DetectionRule):
    name = "interface_state"
    event_types = frozenset({EventType.INTERFACE_DOWN, EventType.INTERFACE_UP})

    def evaluate(self, event, db: Session, config: DetectionConfig):
        is_down = event.event_type_code == EventType.INTERFACE_DOWN.value
        interface = event.interface_name or "unknown"
        host = self._host(event)
        if is_down:
            yield DetectionResult(
                event_type=EventType.INTERFACE_DOWN,
                severity=AlertSeverity.HIGH,
                title=f"Interface {interface} is DOWN on {host}",
                message=event.message,
                dedupe_key=f"INTERFACE_DOWN:{self._device_part(event)}:{interface}",
                context={
                    "interface": interface,
                    "vendor": event.vendor,
                    "source_ip": event.source_ip,
                },
                rule_name=self.name,
            )
        else:
            yield DetectionResult(
                event_type=EventType.INTERFACE_UP,
                severity=AlertSeverity.INFO,
                title=f"Interface {interface} is UP on {host}",
                message=event.message,
                dedupe_key=f"INTERFACE_UP:{self._device_part(event)}:{interface}",
                context={
                    "interface": interface,
                    "vendor": event.vendor,
                    "source_ip": event.source_ip,
                },
                rule_name=self.name,
            )


class LinkFlapRule(DetectionRule):
    name = "link_flap"
    event_types = frozenset({EventType.INTERFACE_DOWN, EventType.INTERFACE_UP})

    def evaluate(self, event, db: Session, config: DetectionConfig):
        if not event.interface_name or not event.device_id:
            return  # flap tracking needs a known device + interface

        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=config.link_flap_window_seconds
        )
        transitions = db.execute(
            select(func.count())
            .select_from(SyslogEvent)
            .where(
                SyslogEvent.device_id == event.device_id,
                SyslogEvent.interface_name == event.interface_name,
                SyslogEvent.event_type_code.in_(
                    [
                        EventType.INTERFACE_DOWN.value,
                        EventType.INTERFACE_UP.value,
                    ]
                ),
                SyslogEvent.received_at >= cutoff,
            )
        ).scalar_one()

        if transitions < config.link_flap_threshold:
            return

        yield DetectionResult(
            event_type=EventType.LINK_FLAP,
            severity=AlertSeverity.CRITICAL,
            title=(
                f"Interface {event.interface_name} flapping on {self._host(event)} "
                f"({transitions} transitions in {config.link_flap_window_seconds}s)"
            ),
            message=event.message,
            dedupe_key=(
                f"LINK_FLAP:{self._device_part(event)}:{event.interface_name}"
            ),
            context={
                "interface": event.interface_name,
                "transitions_in_window": transitions,
                "window_seconds": config.link_flap_window_seconds,
                "threshold": config.link_flap_threshold,
                "vendor": event.vendor,
            },
            rule_name=self.name,
        )
