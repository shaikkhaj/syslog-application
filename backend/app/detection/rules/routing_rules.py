"""Routing detection: BGP/OSPF neighbor state transitions and route changes.

Neighbor extractors are vendor-aware (Cisco ``neighbor 10.0.0.1``,
Juniper ``BGP - 10.0.0.1`` / ``OSPF neighbor 10.0.0.1``) with a generic
fallback so new vendors keep working without rule changes. Transition
tracking derives the previous state from earlier events for the same
neighbor — no extra state tables required.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detection.config import DetectionConfig
from app.detection.rules.base import DetectionRule
from app.detection.types import AlertSeverity, DetectionResult, EventType
from app.models.models import SyslogEvent

_IPV4 = r"\d{1,3}(?:\.\d{1,3}){3}"

# Vendor-specific neighbor extraction, tried in order.
_BGP_EXTRACTORS = [
    re.compile(r"neighbor\s+(" + _IPV4 + r"|\S+)", re.IGNORECASE),  # Cisco/IOS
    re.compile(r"BGP\s*[-–]\s*(" + _IPV4 + r")", re.IGNORECASE),  # Juniper rpd
]
_OSPF_EXTRACTORS = [
    re.compile(r"Nbr\s+(" + _IPV4 + r")", re.IGNORECASE),  # Cisco %OSPF-5-ADJCHG
    re.compile(r"OSPF\s+neighbor\s+(" + _IPV4 + r")", re.IGNORECASE),  # Juniper
]
_ROUTE_EXTRACTORS = [
    re.compile(_IPV4 + r"/\d{1,2}"),  # CIDR prefix
]


def _extract(patterns: list[re.Pattern], message: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(message)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    return None


def _previous_state(
    db: Session, event: SyslogEvent, event_types: list[EventType], key: str | None
) -> str | None:
    """Return 'up'/'down' based on the most recent earlier event of the pair."""
    stmt = (
        select(SyslogEvent)
        .where(
            SyslogEvent.device_id == event.device_id,
            SyslogEvent.event_type_code.in_([t.value for t in event_types]),
            SyslogEvent.id != event.id,
        )
        .order_by(SyslogEvent.received_at.desc(), SyslogEvent.id.desc())
        .limit(1)
    )
    if key:
        stmt = stmt.where(SyslogEvent.message.contains(key))
    earlier = db.execute(stmt).scalar_one_or_none()
    if earlier is None:
        return None
    if earlier.event_type_code in (
        EventType.BGP_UP.value,
        EventType.OSPF_NEIGHBOR_UP.value,
    ):
        return "up"
    return "down"


class BgpStateRule(DetectionRule):
    name = "bgp_state"
    event_types = frozenset({EventType.BGP_DOWN, EventType.BGP_UP})

    def evaluate(self, event, db: Session, config: DetectionConfig):
        neighbor = _extract(_BGP_EXTRACTORS, event.message)
        went_down = event.event_type_code == EventType.BGP_DOWN.value
        previous = _previous_state(
            db, event, [EventType.BGP_DOWN, EventType.BGP_UP], neighbor
        )
        new_state = "down" if went_down else "up"
        host = self._host(event)
        label = neighbor or "unknown neighbor"
        yield DetectionResult(
            event_type=EventType.BGP_DOWN if went_down else EventType.BGP_UP,
            severity=AlertSeverity.HIGH if went_down else AlertSeverity.INFO,
            title=f"BGP neighbor {label} {'DOWN' if went_down else 'UP'} on {host}",
            message=event.message,
            dedupe_key=(
                f"{'BGP_DOWN' if went_down else 'BGP_UP'}:"
                f"{self._device_part(event)}:{neighbor or 'unknown'}"
            ),
            context={
                "neighbor": neighbor,
                "previous_state": previous,
                "new_state": new_state,
                "vendor": event.vendor,
            },
            rule_name=self.name,
        )


class OspfStateRule(DetectionRule):
    name = "ospf_state"
    event_types = frozenset(
        {EventType.OSPF_NEIGHBOR_DOWN, EventType.OSPF_NEIGHBOR_UP}
    )

    def evaluate(self, event, db: Session, config: DetectionConfig):
        neighbor = _extract(_OSPF_EXTRACTORS, event.message)
        went_down = event.event_type_code == EventType.OSPF_NEIGHBOR_DOWN.value
        previous = _previous_state(
            db, event, [EventType.OSPF_NEIGHBOR_DOWN, EventType.OSPF_NEIGHBOR_UP],
            neighbor,
        )
        host = self._host(event)
        label = neighbor or "unknown neighbor"
        yield DetectionResult(
            event_type=(
                EventType.OSPF_NEIGHBOR_DOWN
                if went_down
                else EventType.OSPF_NEIGHBOR_UP
            ),
            severity=AlertSeverity.HIGH if went_down else AlertSeverity.INFO,
            title=f"OSPF neighbor {label} {'DOWN' if went_down else 'UP'} on {host}",
            message=event.message,
            dedupe_key=(
                f"{'OSPF_NEIGHBOR_DOWN' if went_down else 'OSPF_NEIGHBOR_UP'}:"
                f"{self._device_part(event)}:{neighbor or 'unknown'}"
            ),
            context={
                "neighbor": neighbor,
                "previous_state": previous,
                "new_state": "down" if went_down else "up",
                "vendor": event.vendor,
            },
            rule_name=self.name,
        )


class RouteChangeRule(DetectionRule):
    name = "route_change"
    event_types = frozenset({EventType.ROUTE_CHANGE})

    def evaluate(self, event, db: Session, config: DetectionConfig):
        route = _extract(_ROUTE_EXTRACTORS, event.message)
        yield DetectionResult(
            event_type=EventType.ROUTE_CHANGE,
            severity=AlertSeverity.LOW,
            title=(
                f"Route {route} changed on {self._host(event)}"
                if route
                else f"Routing table change on {self._host(event)}"
            ),
            message=event.message,
            dedupe_key=(
                f"ROUTE_CHANGE:{self._device_part(event)}:{route or 'any'}"
            ),
            context={"route": route, "vendor": event.vendor},
            rule_name=self.name,
        )
