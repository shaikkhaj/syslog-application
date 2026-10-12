"""Correlation rules: score how well an alert fits a candidate incident.

Each rule inspects one dimension (same device, interface, subsystem, event
type, source/destination relationship, correlation key) and returns a
configurable weight. The engine sums rule scores and joins the incident when
the total reaches ``min_match_score``.

Adding a rule = subclass :class:`CorrelationRule` and append it to
``DEFAULT_CORRELATION_RULES`` — the engine never changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.correlation.config import CorrelationConfig
from app.correlation.types import CONSEQUENCE_TYPES, PRIMARY_FAILURE_TYPES
from app.detection.types import category_of

_ENDPOINT_CONTEXT_KEYS = ("neighbor", "target")


def alert_interface(alert) -> str | None:
    context = alert.context or {}
    value = context.get("interface")
    return str(value) if value else None


def alert_endpoints(alert) -> set[str]:
    """Shared source/destination style identifiers (peer/neighbor/target IPs)."""
    context = alert.context or {}
    endpoints = set()
    for key in _ENDPOINT_CONTEXT_KEYS:
        value = context.get(key)
        if value:
            endpoints.add(str(value))
    return endpoints


def alert_key(alert) -> str:
    """Deterministic correlation key for an alert.

    Precedence: device+interface -> shared endpoint -> device+subsystem ->
    type. Two alerts describing the same underlying failure derive the same
    key, which powers duplicate-incident prevention.
    """
    interface = alert_interface(alert)
    if interface:
        return f"device:{alert.device_id}:interface:{interface}"
    endpoints = alert_endpoints(alert)
    if endpoints:
        return f"endpoint:{sorted(endpoints)[0]}"
    if alert.device_id:
        return f"device:{alert.device_id}:category:{category_of(alert.event_type)}"
    return f"type:{alert.event_type}"


@dataclass
class IncidentSnapshot:
    """Aggregated view of an incident used for matching."""

    incident_id: int
    correlation_key: str
    device_ids: set[int] = field(default_factory=set)
    interfaces: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    event_types: set[str] = field(default_factory=set)
    endpoints: set[str] = field(default_factory=set)


class CorrelationRule:
    """Base class: returns a weight contribution (0 when it does not match)."""

    name: str = "rule"

    def score(self, alert, snapshot: IncidentSnapshot, config: CorrelationConfig) -> float:
        raise NotImplementedError


class SameCorrelationKeyRule(CorrelationRule):
    """Strongest signal: identical derived key (duplicate-failure guard)."""

    name = "same_correlation_key"

    def score(self, alert, snapshot, config):
        return (
            config.weight_same_key
            if alert_key(alert) == snapshot.correlation_key
            else 0.0
        )


class SameDeviceInterfaceRule(CorrelationRule):
    name = "same_device_interface"

    def score(self, alert, snapshot, config):
        interface = alert_interface(alert)
        if not interface or alert.device_id is None:
            return 0.0
        if alert.device_id in snapshot.device_ids and interface in snapshot.interfaces:
            return config.weight_same_device_interface
        return 0.0


class SameDeviceEventTypeRule(CorrelationRule):
    name = "same_device_event_type"

    def score(self, alert, snapshot, config):
        if alert.device_id is None or alert.device_id not in snapshot.device_ids:
            return 0.0
        return (
            config.weight_same_device_event_type
            if alert.event_type in snapshot.event_types
            else 0.0
        )


class SameDeviceSubsystemRule(CorrelationRule):
    """Same device, same subsystem (interface/routing/security/...)."""

    name = "same_device_subsystem"

    def score(self, alert, snapshot, config):
        if alert.device_id is None or alert.device_id not in snapshot.device_ids:
            return 0.0
        return (
            config.weight_same_device_subsystem
            if category_of(alert.event_type) in snapshot.categories
            else 0.0
        )


class CausalChainRule(CorrelationRule):
    """Failure <-> consequence pairs on the same device.

    Implements the classic pattern: INTERFACE_DOWN + unreachable/route/VPN
    symptoms on one device belong to the same incident.
    """

    name = "causal_chain"

    def score(self, alert, snapshot, config):
        if alert.device_id is None or alert.device_id not in snapshot.device_ids:
            return 0.0
        if alert.event_type in PRIMARY_FAILURE_TYPES and (
            snapshot.event_types & CONSEQUENCE_TYPES
        ):
            return config.weight_causal_chain
        if alert.event_type in CONSEQUENCE_TYPES and (
            snapshot.event_types & PRIMARY_FAILURE_TYPES
        ):
            return config.weight_causal_chain
        return 0.0


class SharedEndpointRule(CorrelationRule):
    """Source/destination relationship: same peer/neighbor/target IP.

    Works across devices (two routers losing the same BGP peer = one
    upstream failure).
    """

    name = "shared_endpoint"

    def score(self, alert, snapshot, config):
        if alert_endpoints(alert) & snapshot.endpoints:
            return config.weight_shared_endpoint
        return 0.0


class CrossDeviceSameTypeRule(CorrelationRule):
    """Same event type on a different device (shared-failure hint).

    Deliberately below ``min_match_score`` alone — it only counts together
    with another dimension (e.g. a shared endpoint).
    """

    name = "cross_device_same_type"

    def score(self, alert, snapshot, config):
        if alert.device_id is None or alert.device_id in snapshot.device_ids:
            return 0.0
        return (
            config.weight_cross_device_same_type
            if alert.event_type in snapshot.event_types
            else 0.0
        )


DEFAULT_CORRELATION_RULES: list[CorrelationRule] = [
    SameCorrelationKeyRule(),
    SameDeviceInterfaceRule(),
    SameDeviceEventTypeRule(),
    SameDeviceSubsystemRule(),
    CausalChainRule(),
    SharedEndpointRule(),
    CrossDeviceSameTypeRule(),
]


def match_score(
    alert,
    snapshot: IncidentSnapshot,
    rules: list[CorrelationRule],
    config: CorrelationConfig,
) -> float:
    """Summed weight of every rule that matches the alert/incident pair."""
    return round(sum(rule.score(alert, snapshot, config) for rule in rules), 3)
