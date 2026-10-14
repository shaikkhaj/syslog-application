"""Network health scoring and advanced RCA helpers (Phase 5).

Submodules:
  * ``scoring`` — pure health-score calculation (device + overall).
  * ``queries``  — shared DB aggregations used by health, RCA and topology.
  * ``rca``      — topology/temporal root-cause device ranking + upstream
                   dependencies built on the Phase 3 candidate list.
"""

from app.health.queries import (
    active_incidents_by_device,
    open_alerts_by_device,
    recent_event_counts,
)
from app.health.rca import (
    DeviceEvidence,
    build_adjacency,
    build_rca_report,
    rank_devices,
    tier_of,
    upstream_dependencies,
)
from app.health.scoring import (
    DeviceSignals,
    HealthConfig,
    band_for,
    compute_device_health,
    compute_overall_health,
)

__all__ = [
    "DeviceEvidence",
    "DeviceSignals",
    "HealthConfig",
    "active_incidents_by_device",
    "band_for",
    "build_adjacency",
    "build_rca_report",
    "compute_device_health",
    "compute_overall_health",
    "open_alerts_by_device",
    "rank_devices",
    "recent_event_counts",
    "tier_of",
    "upstream_dependencies",
]
