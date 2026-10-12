"""Detection engine: runs registered rules against stored events.

The engine is deliberately dumb about specific detections — it only:

1. selects the rules that apply to the event (type + vendor),
2. evaluates them in isolation (a failing rule never breaks ingestion),
3. persists findings through the dedupe-aware alert service,
4. broadcasts created/updated alerts to WebSocket subscribers.

Adding a rule never requires touching this module or the pipeline.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.detection.alert_service import raise_alert
from app.detection.config import DetectionConfig
from app.detection.rules import DEFAULT_RULES, DetectionRule
from app.detection.types import DetectionResult
from app.models.models import SyslogEvent
from app.realtime.broadcaster import alert_broadcaster

logger = logging.getLogger(__name__)


class EngineStats(BaseModel):
    """Thread-safe counters exposed by the health endpoint."""

    alerts_created: int = 0
    alerts_updated: int = 0
    rule_errors: int = 0
    events_processed: int = 0
    last_alert_at: datetime | None = None


class DetectionEngine:
    def __init__(
        self,
        rules: list[DetectionRule] | None = None,
        config: DetectionConfig | None = None,
        broadcaster=None,
    ) -> None:
        self.rules = rules if rules is not None else list(DEFAULT_RULES)
        self.config = config or DetectionConfig.from_settings(get_settings())
        self.broadcaster = broadcaster if broadcaster is not None else alert_broadcaster
        self._lock = threading.Lock()
        self.stats = EngineStats()

    # ------------------------------------------------------------------

    def _bump(self, field: str) -> None:
        with self._lock:
            setattr(self.stats, field, getattr(self.stats, field) + 1)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.stats.model_dump(mode="json")

    def process(self, event: SyslogEvent, db: Session) -> list[dict]:
        """Evaluate all applicable rules for one stored event.

        Safe to call from worker threads. Returns the broadcast payloads of
        the alerts created/updated by this event (useful for tests).
        """
        if not self.config.enabled:
            return []

        self._bump("events_processed")
        payloads: list[dict[str, Any]] = []
        pending_alerts: list[Any] = []
        for rule in self.rules:
            if not rule.applies_to(event):
                continue
            try:
                results = list(rule.evaluate(event, db, self.config) or [])
            except Exception:
                self._bump("rule_errors")
                logger.exception("Detection rule %s failed", rule.name)
                continue
            for result in results:
                outcome = self._persist(result, event, db)
                if outcome is not None:
                    alert, payload = outcome
                    payloads.append(payload)
                    pending_alerts.append(alert)
        if payloads:
            db.commit()  # alerts durable before correlation runs

        # Phase 3: correlate the committed alerts into incidents.
        if pending_alerts:
            try:
                from app.correlation import get_correlation_engine

                payloads.extend(
                    get_correlation_engine().process_alerts(pending_alerts, db)
                )
            except Exception:  # pragma: no cover - correlation must not break ingestion
                logger.exception("Correlation failed for event %s", event.id)
                db.rollback()

        # Broadcast only after every write is committed.
        for payload in payloads:
            self.broadcaster.emit(payload)
        return payloads

    # ------------------------------------------------------------------

    def _persist(
        self, result: DetectionResult, event: SyslogEvent, db: Session
    ) -> tuple[Any, dict[str, Any]] | None:
        try:
            alert, created = raise_alert(db, result, event)
        except Exception:
            self._bump("rule_errors")
            logger.exception("Failed to persist alert for rule %s", result.rule_name)
            db.rollback()
            return None

        action = "created" if created else "updated"
        with self._lock:
            if created:
                self.stats.alerts_created += 1
            else:
                self.stats.alerts_updated += 1
            self.stats.last_alert_at = datetime.now(timezone.utc)

        payload = {
            "type": "alert",
            "action": action,
            "alert": _serialize_alert(alert, event),
        }
        return alert, payload


def _serialize_alert(alert, event: SyslogEvent) -> dict[str, Any]:
    return {
        "id": alert.id,
        "event_type": alert.event_type,
        "severity": alert.severity,
        "status": alert.status,
        "title": alert.title,
        "message": alert.message,
        "rule_name": alert.rule_name,
        "dedupe_key": alert.dedupe_key,
        "event_count": alert.event_count,
        "context": alert.context,
        "device_id": alert.device_id,
        "event_id": alert.event_id,
        "hostname": event.hostname,
        "source_ip": event.source_ip,
        "first_seen_at": alert.first_seen_at.isoformat()
        if alert.first_seen_at
        else None,
        "last_seen_at": alert.last_seen_at.isoformat()
        if alert.last_seen_at
        else None,
    }


# ---------------------------------------------------------------------------
# Process-wide default engine (used by the ingestion pipeline).
# ---------------------------------------------------------------------------

_default_engine: DetectionEngine | None = None
_default_lock = threading.Lock()


def get_detection_engine() -> DetectionEngine:
    """Return (creating once) the default engine built from settings."""
    global _default_engine
    with _default_lock:
        if _default_engine is None:
            _default_engine = DetectionEngine()
            logger.info(
                "Detection engine ready: %s rules, enabled=%s",
                len(_default_engine.rules),
                _default_engine.config.enabled,
            )
    return _default_engine


def reset_detection_engine() -> None:
    """Drop the cached default engine (tests rebuild it from settings)."""
    global _default_engine
    with _default_lock:
        _default_engine = None
