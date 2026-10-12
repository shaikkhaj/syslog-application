"""Incident scoring and ranked root-cause analysis (deterministic, no LLM).

Both functions are pure: they take the incident's member alerts plus the
primary device hostname and return numbers/candidates, so they are trivially
unit-testable and reproducible.
"""

from __future__ import annotations

from app.correlation.config import CorrelationConfig
from app.correlation.types import (
    SEVERITY_POINTS,
    as_utc,
    incident_severity_from_alert,
)

# Relative importance of event types (0..10) for scoring.
EVENT_TYPE_WEIGHTS: dict[str, int] = {
    "INTERFACE_DOWN": 10,
    "DEVICE_UNREACHABLE": 10,
    "BGP_DOWN": 9,
    "VPN_DISCONNECT": 9,
    "OSPF_NEIGHBOR_DOWN": 8,
    "LINK_FLAP": 8,
    "SYSTEM_RESTART": 7,
    "AUTH_FAILURE": 7,
    "CPU_HIGH": 6,
    "MEMORY_HIGH": 6,
    "ROUTE_CHANGE": 5,
    "CONFIG_CHANGE": 4,
    "INTERFACE_ERROR": 4,
    "INTERFACE_UP": 2,
    "BGP_UP": 2,
    "OSPF_NEIGHBOR_UP": 2,
    "OTHER": 3,
}


def is_critical_device(hostname: str | None, config: CorrelationConfig) -> bool:
    """True when the hostname matches a configured importance keyword."""
    if not hostname:
        return False
    lowered = hostname.lower()
    return any(keyword in lowered for keyword in config.critical_keywords())


def compute_incident_score(
    alerts: list,
    hostname: str | None,
    config: CorrelationConfig,
) -> float:
    """Composite score: volume + severity + frequency + importance + type + duration."""
    if not alerts:
        return 0.0

    count = len(alerts)
    volume = sum(max(alert.event_count or 1, 1) for alert in alerts)
    severity_points = max(
        SEVERITY_POINTS[incident_severity_from_alert(alert.severity).value]
        for alert in alerts
    )
    first_seen = min(as_utc(alert.first_seen_at) for alert in alerts)
    last_seen = max(as_utc(alert.last_seen_at) for alert in alerts)
    duration_minutes = max((last_seen - first_seen).total_seconds() / 60.0, 0.0)
    frequency = volume / max(duration_minutes, 1.0)
    importance = 1.0 if is_critical_device(hostname, config) else 0.0
    type_weight = max(
        EVENT_TYPE_WEIGHTS.get(alert.event_type, 3) for alert in alerts
    ) / 10.0

    score = (
        config.score_alert_weight * min(count, 10)
        + config.score_severity_weight * severity_points
        + config.score_frequency_weight * min(frequency, 5.0)
        + config.score_device_importance_weight * importance
        + config.score_event_type_weight * type_weight
        + config.score_duration_weight * min(duration_minutes, 60.0)
    )
    return round(score, 2)


def _has(alerts: list, event_type: str) -> bool:
    return any(alert.event_type == event_type for alert in alerts)


def rank_root_causes(
    alerts: list, hostname: str | None, config: CorrelationConfig
) -> list[dict]:
    """Rank probable root causes from the incident's alert mix.

    Returns candidates ordered by confidence (desc); the first entry is the
    selected root cause. Each candidate carries the evidence (event types and
    counts) that triggered it so operators can audit the reasoning.
    """
    if not alerts:
        return []

    devices = {alert.device_id for alert in alerts if alert.device_id}
    counts: dict[str, int] = {}
    for alert in alerts:
        counts[alert.event_type] = counts.get(alert.event_type, 0) + max(
            alert.event_count or 1, 1
        )

    def evidence_for(*event_types: str) -> list[dict]:
        return [
            {"event_type": event_type, "count": counts[event_type]}
            for event_type in event_types
            if event_type in counts
        ]

    candidates: list[dict] = []

    def add(code: str, title: str, description: str, confidence: float, *ev: str) -> None:
        candidates.append(
            {
                "code": code,
                "title": title,
                "description": description,
                "confidence": round(min(confidence, 0.99), 2),
                "evidence": evidence_for(*ev),
            }
        )

    # Upstream/ISP outage: several devices lose connectivity together.
    if len(devices) >= 2 and (
        _has(alerts, "BGP_DOWN") or _has(alerts, "DEVICE_UNREACHABLE")
    ):
        add(
            "upstream_isp_outage",
            "Upstream / ISP outage",
            "Multiple devices lost connectivity at the same time - likely a "
            "shared upstream or ISP failure.",
            0.90 + 0.03 * min(len(devices) - 1, 3),
            "BGP_DOWN",
            "DEVICE_UNREACHABLE",
            "VPN_DISCONNECT",
        )

    # Local interface failure with corroborating downstream symptoms.
    if _has(alerts, "INTERFACE_DOWN") or _has(alerts, "LINK_FLAP"):
        confidence = 0.80
        ev: list[str] = ["INTERFACE_DOWN", "LINK_FLAP"]
        if _has(alerts, "ROUTE_CHANGE"):
            confidence += 0.07
            ev.append("ROUTE_CHANGE")
        if _has(alerts, "DEVICE_UNREACHABLE"):
            confidence += 0.07
            ev.append("DEVICE_UNREACHABLE")
        if _has(alerts, "VPN_DISCONNECT"):
            confidence += 0.04
            ev.append("VPN_DISCONNECT")
        add(
            "interface_failure",
            "Interface / link failure",
            "A local interface went down or flapped; downstream reachability "
            "and routing changes are consistent with this failure.",
            confidence,
            *ev,
        )

    if _has(alerts, "BGP_DOWN"):
        add(
            "bgp_peer_failure",
            "BGP peer session failure",
            "A BGP adjacency dropped; routing changes followed the session loss.",
            0.78 + (0.07 if _has(alerts, "ROUTE_CHANGE") else 0.0),
            "BGP_DOWN",
            "BGP_UP",
            "ROUTE_CHANGE",
        )

    if _has(alerts, "OSPF_NEIGHBOR_DOWN"):
        add(
            "ospf_adjacency_failure",
            "OSPF adjacency failure",
            "An OSPF neighbor adjacency left the Full state.",
            0.76 + (0.07 if _has(alerts, "ROUTE_CHANGE") else 0.0),
            "OSPF_NEIGHBOR_DOWN",
            "OSPF_NEIGHBOR_UP",
            "ROUTE_CHANGE",
        )

    if _has(alerts, "VPN_DISCONNECT"):
        add(
            "vpn_tunnel_failure",
            "VPN tunnel failure",
            "An IPSec/VPN tunnel disconnected.",
            0.80,
            "VPN_DISCONNECT",
        )

    if _has(alerts, "AUTH_FAILURE"):
        failures = counts.get("AUTH_FAILURE", 0)
        add(
            "brute_force_authentication",
            "Repeated authentication failures",
            "Sustained failed logins suggest brute-force or credential abuse.",
            0.70 + min(failures, 25) / 100.0,
            "AUTH_FAILURE",
        )

    if _has(alerts, "CPU_HIGH") or _has(alerts, "MEMORY_HIGH"):
        add(
            "resource_exhaustion",
            "Resource exhaustion",
            "High CPU or memory utilization can degrade forwarding and control "
            "planes.",
            0.65,
            "CPU_HIGH",
            "MEMORY_HIGH",
        )

    if _has(alerts, "CONFIG_CHANGE"):
        add(
            "unauthorized_configuration_change",
            "Configuration change",
            "A configuration change correlates with the observed symptoms.",
            0.55,
            "CONFIG_CHANGE",
        )

    if _has(alerts, "DEVICE_UNREACHABLE") and not (
        _has(alerts, "INTERFACE_DOWN")
        or _has(alerts, "BGP_DOWN")
        or _has(alerts, "VPN_DISCONNECT")
    ):
        add(
            "path_reachability_failure",
            "Path reachability failure",
            "A host or network path is reported unreachable without a local "
            "link failure.",
            0.68,
            "DEVICE_UNREACHABLE",
        )

    if _has(alerts, "ROUTE_CHANGE") and not (
        _has(alerts, "BGP_DOWN")
        or _has(alerts, "OSPF_NEIGHBOR_DOWN")
        or _has(alerts, "INTERFACE_DOWN")
    ):
        add(
            "route_instability",
            "Routing table instability",
            "Route additions/removals without an obvious adjacency failure.",
            0.60,
            "ROUTE_CHANGE",
        )

    if not candidates:
        add(
            "undetermined",
            "Undetermined cause",
            "Insufficient correlated evidence to rank a probable root cause.",
            0.30,
            *counts.keys(),
        )

    candidates.sort(key=lambda candidate: (-candidate["confidence"], candidate["code"]))
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    return candidates
