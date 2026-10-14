"""Advanced root-cause analysis (Phase 5): probable culprit devices.

Phase 3 ranks *failure modes* (``rank_root_causes``); Phase 5 answers the
complementary question — *which device* is the probable root cause and what
it depends on upstream. Deterministic, reusing existing data only:

  * the Phase 3 candidate list (stored on the incident, recomputed if absent);
  * member-alert evidence per device (severity, event types, timestamps);
  * topology links traversed with a BFS that only walks toward lower device
    tiers (firewall → router → switch → server = upstream direction);
  * the incident's primary device and configured critical-device keywords.

Every scoring step appends a human-readable reason so the API/UI can show
the explanation instead of an opaque number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.correlation.config import CorrelationConfig
from app.correlation.scoring import is_critical_device, rank_root_causes
from app.correlation.types import CONSEQUENCE_TYPES, PRIMARY_FAILURE_TYPES, as_utc
from app.models.models import Alert, Device, Incident, TopologyLink

# Device hierarchy: lower tier = closer to the core = upstream.
DEVICE_TIERS: dict[str, int] = {"firewall": 0, "router": 1, "switch": 2, "server": 3}
DEFAULT_TIER = 1

# Per-member-alert importance for device ranking (0..10).
_RCA_SEVERITY_POINTS: dict[str, int] = {
    "CRITICAL": 10,
    "HIGH": 8,
    "MEDIUM": 5,
    "LOW": 3,
    "INFO": 1,
}
_RCA_SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

# Fixed bonuses (single source of truth so tests assert exact scores).
BONUS_EARLIEST = 6.0  # device that raised the first alert of the incident
BONUS_FAILURE_TYPE = 4.0  # per distinct primary failure signal (max 2)
BONUS_CONSEQUENCE_TYPE = 1.0  # per distinct consequence signal (max 3)
BONUS_UPSTREAM_OF_ALERTING = 3.0  # adjacent, strictly lower tier than peer
BONUS_ALERTING_PEER = 1.0  # adjacent, same tier, alerting peer
BONUS_INCIDENT_PRIMARY = 2.0  # incident.device_id
BONUS_CRITICAL_DEVICE = 2.0  # hostname matches critical keywords


def tier_of(device_type: str | None) -> int:
    """Hierarchy tier for a device type (lower = more upstream)."""
    return DEVICE_TIERS.get((device_type or "").lower(), DEFAULT_TIER)


def build_adjacency(links) -> dict[int, set[int]]:
    """Undirected device-id adjacency from topology links (self loops dropped)."""
    adjacency: dict[int, set[int]] = {}
    for link in links:
        source = link.source_device_id
        target = link.target_device_id
        if source is None or target is None or source == target:
            continue
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
    return adjacency


@dataclass
class DeviceEvidence:
    """Aggregated member-alert evidence for one device inside an incident."""

    device_id: int
    severities: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)
    first_seen: datetime | None = None
    is_incident_primary: bool = False
    is_critical: bool = False


def _label(device_id: int, labels: dict[int, str] | None) -> str:
    if labels and device_id in labels:
        return labels[device_id]
    return f"device {device_id}"


def _max_severity(severities: list[str]) -> str:
    ranked = [s for s in severities if s in _RCA_SEVERITY_ORDER]
    if not ranked:
        return severities[0] if severities else "INFO"
    return max(ranked, key=lambda value: _RCA_SEVERITY_ORDER.index(value))


def rank_devices(
    evidence: dict[int, DeviceEvidence],
    adjacency: dict[int, set[int]] | None = None,
    tiers: dict[int, int] | None = None,
    labels: dict[int, str] | None = None,
) -> list[dict]:
    """Rank probable root-cause devices from evidence + topology + timing.

    Pure function: returns entries ordered by score desc (device id asc on
    ties) with ``rank``, ``device_id``, ``score`` and audit ``reasons``.
    """
    if not evidence:
        return []
    adjacency = adjacency or {}
    tiers = tiers or {}

    earliest = min(
        (as_utc(ev.first_seen) for ev in evidence.values() if ev.first_seen),
        default=None,
    )

    scored: list[dict] = []
    for device_id, ev in evidence.items():
        reasons: list[str] = []
        score = 0.0

        if ev.severities:
            severity_points = sum(
                _RCA_SEVERITY_POINTS.get(severity, 1) for severity in ev.severities
            )
            score += severity_points
            reasons.append(
                f"{len(ev.severities)} member alert(s), max severity "
                f"{_max_severity(ev.severities)} (+{severity_points})"
            )

        primary_types = {t for t in ev.event_types if t in PRIMARY_FAILURE_TYPES}
        consequence_types = {
            t
            for t in ev.event_types
            if t in CONSEQUENCE_TYPES and t not in primary_types
        }
        failure_bonus = BONUS_FAILURE_TYPE * min(len(primary_types), 2)
        if failure_bonus:
            score += failure_bonus
            reasons.append(
                f"primary failure signal {', '.join(sorted(primary_types))} "
                f"(+{failure_bonus:g})"
            )
        consequence_bonus = BONUS_CONSEQUENCE_TYPE * min(len(consequence_types), 3)
        if consequence_bonus:
            score += consequence_bonus
            reasons.append(
                f"consequence evidence {', '.join(sorted(consequence_types))} "
                f"(+{consequence_bonus:g})"
            )

        if earliest is not None and ev.first_seen and as_utc(ev.first_seen) == earliest:
            score += BONUS_EARLIEST
            reasons.append(
                f"raised the first alert of the incident (+{BONUS_EARLIEST:g})"
            )

        own_tier = tiers.get(device_id, DEFAULT_TIER)
        for other_id in evidence:
            if other_id == device_id or other_id not in adjacency.get(device_id, set()):
                continue
            other_tier = tiers.get(other_id, DEFAULT_TIER)
            if own_tier < other_tier:
                score += BONUS_UPSTREAM_OF_ALERTING
                reasons.append(
                    f"topology: upstream of alerting "
                    f"{_label(other_id, labels)} (+{BONUS_UPSTREAM_OF_ALERTING:g})"
                )
            elif own_tier == other_tier:
                score += BONUS_ALERTING_PEER
                reasons.append(
                    f"topology: linked alerting peer "
                    f"{_label(other_id, labels)} (+{BONUS_ALERTING_PEER:g})"
                )

        if ev.is_incident_primary:
            score += BONUS_INCIDENT_PRIMARY
            reasons.append(
                f"incident primary device (+{BONUS_INCIDENT_PRIMARY:g})"
            )
        if ev.is_critical:
            score += BONUS_CRITICAL_DEVICE
            reasons.append(
                f"configured critical-device keyword (+{BONUS_CRITICAL_DEVICE:g})"
            )

        scored.append(
            {"device_id": device_id, "score": round(score, 2), "reasons": reasons}
        )

    scored.sort(key=lambda entry: (-entry["score"], entry["device_id"]))
    for rank, entry in enumerate(scored, start=1):
        entry["rank"] = rank
    return scored


def upstream_dependencies(
    primary_id: int,
    adjacency: dict[int, set[int]],
    tiers: dict[int, int],
    labels: dict[int, str] | None = None,
    max_hops: int = 3,
) -> list[dict]:
    """Devices the primary suspect depends on upstream (BFS toward the core).

    Traversal only continues through nodes at or below the primary's tier;
    only strictly-lower-tier nodes are reported as upstream dependencies.
    """
    primary_tier = tiers.get(primary_id, DEFAULT_TIER)
    visited = {primary_id}
    frontier = [primary_id]
    results: list[dict] = []
    hops = 0

    while frontier and hops < max_hops:
        hops += 1
        next_frontier: list[int] = []
        for node in frontier:
            for neighbor in sorted(adjacency.get(node, set())):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                neighbor_tier = tiers.get(neighbor, DEFAULT_TIER)
                if neighbor_tier > primary_tier:
                    continue  # downstream of the suspect — not a dependency
                next_frontier.append(neighbor)
                if neighbor_tier < primary_tier:
                    results.append(
                        {
                            "device_id": neighbor,
                            "hops": hops,
                            "device_type": "unknown",
                            "reason": (
                                f"{hops} hop(s) upstream of "
                                f"{_label(primary_id, labels)}"
                            ),
                        }
                    )
        frontier = next_frontier
    return results


def _primary_hostname(incident: Incident, devices: dict[int, Device]) -> str | None:
    """Mirror the engine's primary-hostname resolution for recomputation."""
    if incident.device_id and incident.device_id in devices:
        return devices[incident.device_id].hostname
    for entry in incident.affected_devices or []:
        device_id = entry.get("device_id")
        if device_id and device_id in devices:
            return devices[device_id].hostname
        if entry.get("hostname"):
            return entry["hostname"]
    return None


def build_rca_report(db: Session, incident: Incident) -> dict:
    """Full RCA report: Phase 3 candidates + device ranking + upstream deps.

    Returns a dict matching ``schemas.network_health.RcaReportResponse``.
    """
    config = CorrelationConfig.from_settings()
    alerts = list(
        db.execute(
            select(Alert)
            .where(Alert.incident_id == incident.id)
            .order_by(Alert.first_seen_at.asc())
        )
        .scalars()
        .all()
    )
    devices = {
        device.id: device for device in db.execute(select(Device)).scalars().all()
    }
    links = list(db.execute(select(TopologyLink)).scalars().all())
    adjacency = build_adjacency(links)
    tiers = {
        device_id: tier_of(device.device_type)
        for device_id, device in devices.items()
    }
    labels = {
        device_id: (device.hostname or device.ip_address)
        for device_id, device in devices.items()
    }

    # Phase 3 candidates: reuse the stored ranking, recompute when missing.
    candidates = list(incident.root_cause_candidates or [])
    if not candidates and alerts:
        candidates = rank_root_causes(
            alerts, _primary_hostname(incident, devices), config
        )

    # Per-device member-alert evidence.
    evidence: dict[int, DeviceEvidence] = {}
    for alert in alerts:
        if alert.device_id is None:
            continue
        ev = evidence.setdefault(
            alert.device_id, DeviceEvidence(device_id=alert.device_id)
        )
        ev.severities.append(alert.severity or "INFO")
        ev.event_types.append(alert.event_type)
        seen = as_utc(alert.first_seen_at)
        if ev.first_seen is None or (seen and seen < as_utc(ev.first_seen)):
            ev.first_seen = alert.first_seen_at
    if incident.device_id is not None:
        evidence.setdefault(
            incident.device_id, DeviceEvidence(device_id=incident.device_id)
        )
    for device_id, ev in evidence.items():
        device = devices.get(device_id)
        ev.is_incident_primary = device_id == incident.device_id
        ev.is_critical = bool(device) and is_critical_device(device.hostname, config)

    ranking = rank_devices(evidence, adjacency, tiers, labels)

    upstream: list[dict] = []
    primary_device_id = ranking[0]["device_id"] if ranking else None
    if primary_device_id is not None:
        upstream = upstream_dependencies(primary_device_id, adjacency, tiers, labels)
        for entry in upstream:
            device = devices.get(entry["device_id"])
            if device is not None:
                entry["device_type"] = device.device_type or "router"
                entry["hostname"] = device.hostname
                entry["ip_address"] = device.ip_address

    for entry in ranking:
        device = devices.get(entry["device_id"])
        entry["hostname"] = device.hostname if device else None
        entry["ip_address"] = device.ip_address if device else None
    for candidate in candidates:
        candidate.setdefault("evidence", [])

    top = candidates[0] if candidates else None
    if primary_device_id is not None and top is not None:
        suspect = labels.get(primary_device_id, f"device {primary_device_id}")
        summary = (
            f"Probable root cause: {suspect} — {top['title']} "
            f"({round(top['confidence'] * 100)}% confidence). "
            f"{len(ranking)} device(s) ranked from {len(alerts)} correlated "
            f"alert(s); {len(upstream)} upstream dependency(ies) identified "
            f"from topology."
        )
    elif primary_device_id is not None:
        suspect = labels.get(primary_device_id, f"device {primary_device_id}")
        summary = (
            f"Probable root cause: {suspect} — insufficient event-type "
            f"evidence to classify the failure mode."
        )
    else:
        summary = "No correlated alert evidence — nothing to analyze yet."

    return {
        "incident_id": incident.id,
        "title": incident.title,
        "status": incident.status,
        "severity": incident.severity,
        "confidence": incident.confidence,
        "summary": summary,
        "candidates": candidates,
        "device_ranking": ranking,
        "upstream_dependencies": upstream,
        "primary_device_id": primary_device_id,
    }
