"""Configurable correlation windows, match weights and scoring weights."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class CorrelationConfig:
    enabled: bool = True
    # Temporal correlation -------------------------------------------------
    time_window_seconds: int = 300
    min_match_score: float = 3.0
    # Match weights (a candidate incident is joined when the summed weight
    # of matching correlation rules reaches min_match_score).
    weight_same_key: float = 5.0
    weight_same_device_interface: float = 4.0
    weight_same_device_event_type: float = 3.5
    weight_same_device_subsystem: float = 3.0
    weight_causal_chain: float = 3.0
    weight_shared_endpoint: float = 3.5
    weight_cross_device_same_type: float = 2.0
    # Device importance ----------------------------------------------------
    critical_device_keywords: str = (
        "core,edge,aggregation,gateway,firewall,router,rtr"
    )
    # Incident scoring ------------------------------------------------------
    score_alert_weight: float = 3.0
    score_severity_weight: float = 10.0
    score_frequency_weight: float = 4.0
    score_device_importance_weight: float = 15.0
    score_event_type_weight: float = 8.0
    score_duration_weight: float = 0.2

    def critical_keywords(self) -> list[str]:
        return [
            keyword.strip().lower()
            for keyword in self.critical_device_keywords.split(",")
            if keyword.strip()
        ]

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "CorrelationConfig":
        settings = settings or get_settings()
        return cls(
            enabled=settings.correlation_enabled,
            time_window_seconds=settings.correlation_window_seconds,
            min_match_score=settings.correlation_min_match_score,
            weight_same_key=settings.correlation_weight_same_key,
            weight_same_device_interface=settings.correlation_weight_same_device_interface,
            weight_same_device_event_type=settings.correlation_weight_same_device_event_type,
            weight_same_device_subsystem=settings.correlation_weight_same_device_subsystem,
            weight_causal_chain=settings.correlation_weight_causal_chain,
            weight_shared_endpoint=settings.correlation_weight_shared_endpoint,
            weight_cross_device_same_type=settings.correlation_weight_cross_device_same_type,
            critical_device_keywords=settings.correlation_critical_device_keywords,
            score_alert_weight=settings.correlation_score_alert_weight,
            score_severity_weight=settings.correlation_score_severity_weight,
            score_frequency_weight=settings.correlation_score_frequency_weight,
            score_device_importance_weight=settings.correlation_score_device_importance_weight,
            score_event_type_weight=settings.correlation_score_event_type_weight,
            score_duration_weight=settings.correlation_score_duration_weight,
        )
