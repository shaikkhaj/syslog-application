"""Configurable thresholds for the detection engine.

Every threshold is environment-configurable (see ``Settings`` in
``app.core.config``) — no rule hardcodes values. Tests build their own
``DetectionConfig`` instances to exercise different thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class DetectionConfig:
    enabled: bool = True
    # Link flap ---------------------------------------------------------
    link_flap_window_seconds: int = 300
    link_flap_threshold: int = 4
    # Authentication failures -------------------------------------------
    auth_failure_window_seconds: int = 300
    auth_failure_threshold: int = 5
    # Device performance -------------------------------------------------
    cpu_high_threshold_percent: int = 90
    memory_high_threshold_percent: int = 90

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "DetectionConfig":
        settings = settings or get_settings()
        return cls(
            enabled=settings.detection_enabled,
            link_flap_window_seconds=settings.link_flap_window_seconds,
            link_flap_threshold=settings.link_flap_threshold,
            auth_failure_window_seconds=settings.auth_failure_window_seconds,
            auth_failure_threshold=settings.auth_failure_threshold,
            cpu_high_threshold_percent=settings.cpu_high_threshold_percent,
            memory_high_threshold_percent=settings.memory_high_threshold_percent,
        )
