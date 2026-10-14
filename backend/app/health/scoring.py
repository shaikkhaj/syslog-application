"""Health-score calculation (Phase 5) — pure and deterministic.

A device's health starts at 100 and is reduced by penalties derived from
existing data only (no stored scores):

  * open (non-resolved) alerts — severity weighted, capped;
  * active incidents — severity weighted, capped;
  * recent syslog event frequency inside the rolling window (noisy devices);
  * administrative status (offline / maintenance).

The overall network score is the plain mean of all device scores, so a
single unhealthy device can never hide behind a healthy majority beyond
its arithmetic weight. Bands: healthy ≥ 80 > degraded ≥ 50 > critical.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _default_alert_penalties() -> dict[str, float]:
    return {"CRITICAL": 35.0, "HIGH": 25.0, "MEDIUM": 12.0, "LOW": 5.0, "INFO": 2.0}


def _default_incident_penalties() -> dict[str, float]:
    return {"CRITICAL": 30.0, "HIGH": 20.0, "MEDIUM": 10.0, "LOW": 4.0}


@dataclass(frozen=True)
class HealthConfig:
    """Weights/thresholds for health scoring (defaults are the shipped ones)."""

    # Rolling window for "recent event frequency".
    window_minutes: int = 60
    # Penalty per open alert, by severity (summed, then capped).
    alert_penalties: dict[str, float] = field(default_factory=_default_alert_penalties)
    alert_penalty_cap: float = 60.0
    # Penalty per active incident, by severity (summed, then capped).
    incident_penalties: dict[str, float] = field(default_factory=_default_incident_penalties)
    incident_penalty_cap: float = 40.0
    # Event frequency: only events above the baseline accrue penalty.
    event_baseline: int = 10
    event_penalty_per_event: float = 0.5
    event_penalty_cap: float = 20.0
    # Device status penalties.
    offline_penalty: float = 25.0
    maintenance_penalty: float = 10.0
    # Band thresholds (score >= healthy_from → healthy, etc.).
    healthy_from: float = 80.0
    degraded_from: float = 50.0

    def band_for(self, score: float) -> str:
        if score >= self.healthy_from:
            return "healthy"
        if score >= self.degraded_from:
            return "degraded"
        return "critical"


def band_for(score: float, config: HealthConfig | None = None) -> str:
    """Classify a 0–100 score into healthy | degraded | critical."""
    return (config or HealthConfig()).band_for(score)


@dataclass
class DeviceSignals:
    """Aggregated signals for one device (produced by ``health.queries``)."""

    device_id: int
    status: str = "active"
    alert_severities: list[str] = field(default_factory=list)
    incident_severities: list[str] = field(default_factory=list)
    recent_event_count: int = 0


def compute_device_health(
    signals: DeviceSignals, config: HealthConfig | None = None
) -> dict:
    """Score one device (0–100, higher is healthier) with a penalty breakdown."""
    config = config or HealthConfig()

    alert_penalty = min(
        sum(config.alert_penalties.get(severity, 5.0) for severity in signals.alert_severities),
        config.alert_penalty_cap,
    )
    incident_penalty = min(
        sum(config.incident_penalties.get(severity, 4.0) for severity in signals.incident_severities),
        config.incident_penalty_cap,
    )
    excess_events = max(signals.recent_event_count - config.event_baseline, 0)
    event_penalty = min(
        excess_events * config.event_penalty_per_event, config.event_penalty_cap
    )
    if signals.status == "offline":
        status_penalty = config.offline_penalty
    elif signals.status == "maintenance":
        status_penalty = config.maintenance_penalty
    else:
        status_penalty = 0.0

    breakdown = {
        "alerts": round(alert_penalty, 2),
        "incidents": round(incident_penalty, 2),
        "events": round(event_penalty, 2),
        "status": round(status_penalty, 2),
    }
    score = round(max(100.0 - sum(breakdown.values()), 0.0), 1)
    return {
        "score": score,
        "band": config.band_for(score),
        "breakdown": breakdown,
    }


def compute_overall_health(
    scores: list[float], config: HealthConfig | None = None
) -> dict:
    """Mean of device scores → overall score, band and per-band counts."""
    config = config or HealthConfig()
    if not scores:
        score, counts = 100.0, {"healthy": 0, "degraded": 0, "critical": 0}
    else:
        score = round(sum(scores) / len(scores), 1)
        counts = {"healthy": 0, "degraded": 0, "critical": 0}
        for value in scores:
            counts[config.band_for(value)] += 1
    return {"score": score, "band": config.band_for(score), "counts": counts}
