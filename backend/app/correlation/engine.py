"""Correlation engine: turns related alerts into incidents.

Flow per alert (alerts arrive from the detection engine after commit):

1. load active incidents with activity inside the configured window;
2. score the alert against each candidate with the correlation rules;
3. best candidate ≥ min_match_score → attach (aggregate, rescore, re-rank
   root causes); otherwise create a new OPEN incident with a correlation key;
4. a partial unique index (one active incident per key) makes duplicate
   creation safe under concurrency — the loser catches IntegrityError and
   attaches instead.

Every state transition appends to ``incident_state_history``; attaches and
creations return WebSocket payloads broadcast by the detection engine.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.correlation.config import CorrelationConfig
from app.correlation.rules import (
    DEFAULT_CORRELATION_RULES,
    CorrelationRule,
    IncidentSnapshot,
    alert_endpoints,
    alert_interface,
    alert_key,
    match_score,
)
from app.correlation.scoring import compute_incident_score, rank_root_causes
from app.correlation.types import (
    RECOVERY_EVENT_TYPES,
    IncidentSeverity,
    IncidentStatus,
    as_utc,
    incident_severity_from_alert,
)
from app.core.config import get_settings
from app.detection.types import AlertStatus, category_of
from app.models.models import (
    Alert,
    Device,
    Incident,
    IncidentAlert,
    IncidentEvent,
    IncidentStateHistory,
    SyslogEvent,
)
from app.realtime.broadcaster import alert_broadcaster

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = IncidentStatus.active()

# Valid lifecycle transitions (state machine).
VALID_TRANSITIONS: dict[str, set[str]] = {
    IncidentStatus.OPEN.value: {
        IncidentStatus.INVESTIGATING.value,
        IncidentStatus.ACKNOWLEDGED.value,
        IncidentStatus.RESOLVED.value,
    },
    IncidentStatus.INVESTIGATING.value: {
        IncidentStatus.ACKNOWLEDGED.value,
        IncidentStatus.RESOLVED.value,
    },
    IncidentStatus.ACKNOWLEDGED.value: {IncidentStatus.RESOLVED.value},
    IncidentStatus.RESOLVED.value: {IncidentStatus.CLOSED.value},
    IncidentStatus.CLOSED.value: set(),
}


class CorrelationStats(BaseModel):
    incidents_created: int = 0
    incidents_updated: int = 0
    alerts_attached: int = 0
    errors: int = 0
    last_incident_at: datetime | None = None


def build_snapshot(db: Session, incident: Incident) -> IncidentSnapshot:
    """Aggregate an incident's member alerts into a matchable snapshot."""
    alerts = (
        db.execute(select(Alert).where(Alert.incident_id == incident.id))
        .scalars()
        .all()
    )
    snapshot = IncidentSnapshot(
        incident_id=incident.id, correlation_key=incident.correlation_key
    )
    for alert in alerts:
        if alert.device_id is not None:
            snapshot.device_ids.add(alert.device_id)
        interface = alert_interface(alert)
        if interface:
            snapshot.interfaces.add(interface)
        snapshot.categories.add(category_of(alert.event_type))
        snapshot.event_types.add(alert.event_type)
        snapshot.endpoints |= alert_endpoints(alert)
    return snapshot


class CorrelationEngine:
    def __init__(
        self,
        rules: list[CorrelationRule] | None = None,
        config: CorrelationConfig | None = None,
        broadcaster=None,
    ) -> None:
        self.rules = rules if rules is not None else list(DEFAULT_CORRELATION_RULES)
        self.config = config or CorrelationConfig.from_settings(get_settings())
        self.broadcaster = broadcaster if broadcaster is not None else alert_broadcaster
        self._lock = threading.Lock()
        self.stats = CorrelationStats()

    # ------------------------------------------------------------------ stats

    def _bump(self, field_name: str) -> None:
        with self._lock:
            setattr(self.stats, field_name, getattr(self.stats, field_name) + 1)

    def _touch(self) -> None:
        with self._lock:
            self.stats.last_incident_at = datetime.now(timezone.utc)

    def snapshot_stats(self) -> dict[str, Any]:
        with self._lock:
            return self.stats.model_dump(mode="json")

    # ------------------------------------------------------------- entry point

    def process_alerts(self, alerts: list[Alert], db: Session) -> list[dict[str, Any]]:
        """Correlate committed alerts into incidents. Commits its own work."""
        if not self.config.enabled:
            return []
        payloads: list[dict[str, Any]] = []
        for alert in alerts:
            if alert.status == AlertStatus.RESOLVED.value:
                continue  # resolved alerts no longer carry incident signal
            try:
                payload = self._process_one(alert, db)
            except Exception:
                self._bump("errors")
                logger.exception("Correlation failed for alert %s", alert.id)
                db.rollback()
                continue
            if payload is not None:
                payloads.append(payload)
        return payloads

    def _process_one(self, alert: Alert, db: Session) -> dict[str, Any] | None:
        alert_time = alert.first_seen_at or alert.created_at or datetime.now(timezone.utc)
        window_start = alert_time - timedelta(seconds=self.config.time_window_seconds)
        candidates = (
            db.execute(
                select(Incident)
                .where(
                    Incident.status.in_(ACTIVE_STATUSES),
                    Incident.last_seen_at >= window_start,
                )
                .order_by(Incident.last_seen_at.desc())
                .limit(50)
            )
            .scalars()
            .all()
        )

        best: Incident | None = None
        best_score = 0.0
        for incident in candidates:
            snapshot = build_snapshot(db, incident)
            score = match_score(alert, snapshot, self.rules, self.config)
            if score >= self.config.min_match_score and score > best_score:
                best, best_score = incident, score

        if best is not None:
            return self._attach(alert, best, db)
        return self._create(alert, db)

    # ---------------------------------------------------------------- create

    def _create(self, alert: Alert, db: Session) -> dict[str, Any]:
        key = alert_key(alert)
        first_seen = alert.first_seen_at or alert.created_at or datetime.now(timezone.utc)
        last_seen = alert.last_seen_at or first_seen
        incident = Incident(
            correlation_key=key,
            title=alert.title[:255],
            status=IncidentStatus.OPEN.value,
            severity=incident_severity_from_alert(alert.severity).value,
            category=category_of(alert.event_type),
            device_id=alert.device_id,
            affected_devices=self._device_entries(db, {alert.device_id}),
            alert_count=1,
            first_seen_at=first_seen,
            last_seen_at=last_seen,
        )
        try:
            db.add(incident)
            db.flush()
        except IntegrityError:
            # Lost a race for the same active correlation key — attach to the
            # winner instead of creating a duplicate incident.
            db.rollback()
            existing = db.execute(
                select(Incident).where(
                    Incident.correlation_key == key,
                    Incident.status.in_(ACTIVE_STATUSES),
                )
            ).scalar_one_or_none()
            if existing is None:  # pragma: no cover - unexpected constraint
                raise
            logger.info(
                "Correlation key race for %s — attaching to incident #%s",
                key,
                existing.id,
            )
            return self._attach(alert, existing, db)

        db.add(
            IncidentStateHistory(
                incident_id=incident.id,
                from_status=None,
                to_status=IncidentStatus.OPEN.value,
                changed_by="correlation",
                note=f"created from alert #{alert.id}",
            )
        )
        self._link_alert(db, incident, alert)
        self._finalize(db, incident)
        db.commit()

        self._bump("incidents_created")
        self._bump("alerts_attached")
        self._touch()
        logger.info(
            "Incident #%s created [%s/%s] score=%s: %s",
            incident.id,
            incident.severity,
            incident.correlation_key,
            incident.score,
            incident.title,
        )
        return _serialize_payload(incident, "created")

    # ---------------------------------------------------------------- attach

    def _attach(self, alert: Alert, incident: Incident, db: Session) -> dict[str, Any]:
        alert_first = as_utc(alert.first_seen_at or alert.created_at)
        alert_last = as_utc(alert.last_seen_at or alert.first_seen_at)
        incident_first = as_utc(incident.first_seen_at)
        incident_last = as_utc(incident.last_seen_at)
        if alert_first and incident_first and alert_first < incident_first:
            incident.first_seen_at = alert_first
        if alert_last and incident_last and alert_last > incident_last:
            incident.last_seen_at = alert_last
        self._merge_devices(db, incident, {alert.device_id})

        alert_severity = incident_severity_from_alert(alert.severity)
        if IncidentSeverity.order(alert_severity) > IncidentSeverity.order(
            incident.severity
        ):
            incident.severity = alert_severity.value

        linked_new = self._link_alert(db, incident, alert)
        self._finalize(db, incident)
        db.commit()

        if linked_new:
            self._bump("alerts_attached")
        self._bump("incidents_updated")
        self._touch()
        logger.info(
            "Alert #%s (%s) correlated into incident #%s",
            alert.id,
            alert.event_type,
            incident.id,
        )
        return _serialize_payload(incident, "updated")

    def _link_alert(self, db: Session, incident: Incident, alert: Alert) -> bool:
        """Join an alert (and its triggering event) to the incident."""
        existing = db.execute(
            select(IncidentAlert).where(IncidentAlert.alert_id == alert.id)
        ).scalar_one_or_none()
        if existing is not None:
            return False
        db.add(IncidentAlert(incident_id=incident.id, alert_id=alert.id))
        alert.incident_id = incident.id
        if alert.event_id:
            event_link = db.execute(
                select(IncidentEvent).where(
                    IncidentEvent.incident_id == incident.id,
                    IncidentEvent.event_id == alert.event_id,
                )
            ).scalar_one_or_none()
            if event_link is None:
                db.add(IncidentEvent(incident_id=incident.id, event_id=alert.event_id))
        return True

    def _finalize(self, db: Session, incident: Incident) -> None:
        """Recompute aggregates, score and ranked root causes."""
        db.flush()  # make pending alert links visible to the queries below
        alerts = list(
            db.execute(select(Alert).where(Alert.incident_id == incident.id))
            .scalars()
            .all()
        )
        hostname = self._primary_hostname(db, incident)
        incident.alert_count = len(alerts)
        incident.score = compute_incident_score(alerts, hostname, self.config)
        candidates = rank_root_causes(alerts, hostname, self.config)
        if candidates:
            top = candidates[0]
            incident.root_cause = f"{top['title']}: {top['description']}"
            incident.confidence = top["confidence"]
            incident.root_cause_candidates = candidates

    # ------------------------------------------------------------- device help

    def _device_entries(
        self, db: Session, device_ids: set[int | None]
    ) -> list[dict[str, Any]]:
        entries = []
        for device_id in sorted(d for d in device_ids if d is not None):
            device = db.get(Device, device_id)
            if device is None:
                continue
            entries.append(
                {
                    "device_id": device.id,
                    "hostname": device.hostname,
                    "ip_address": device.ip_address,
                }
            )
        return entries

    def _merge_devices(
        self, db: Session, incident: Incident, device_ids: set[int | None]
    ) -> None:
        known = {entry.get("device_id") for entry in (incident.affected_devices or [])}
        for entry in self._device_entries(db, device_ids - known):
            incident.affected_devices = (incident.affected_devices or []) + [entry]

    def _primary_hostname(self, db: Session, incident: Incident) -> str | None:
        if incident.device_id:
            device = db.get(Device, incident.device_id)
            if device is not None:
                return device.hostname
        entries = incident.affected_devices or []
        return entries[0].get("hostname") if entries else None

    # ------------------------------------------------------------- lifecycle

    def transition_status(
        self,
        incident: Incident,
        to_status: IncidentStatus,
        db: Session,
        actor: str = "api-user",
        note: str | None = None,
    ) -> None:
        """Move an incident through the state machine (raises ValueError)."""
        target = to_status.value if isinstance(to_status, IncidentStatus) else to_status
        allowed = VALID_TRANSITIONS.get(incident.status, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid transition {incident.status} -> {target}"
            )

        now = datetime.now(timezone.utc)
        history_kwargs: dict[str, Any] = {}
        if target == IncidentStatus.ACKNOWLEDGED.value:
            incident.acknowledged_at = now
            incident.acknowledged_by = actor
            history_kwargs["note"] = note or "acknowledged"
        elif target == IncidentStatus.RESOLVED.value:
            incident.resolved_at = now
            if incident.acknowledged_at is None:
                incident.acknowledged_at = now
                incident.acknowledged_by = actor
            history_kwargs["note"] = note or "resolved"
        elif target == IncidentStatus.CLOSED.value:
            incident.closed_at = now
            history_kwargs["note"] = note or "closed"

        previous = incident.status
        incident.status = target
        db.add(
            IncidentStateHistory(
                incident_id=incident.id,
                from_status=previous,
                to_status=target,
                changed_by=actor,
                **history_kwargs,
            )
        )
        db.commit()
        logger.info(
            "Incident #%s %s -> %s by %s", incident.id, previous, target, actor
        )

    # --------------------------------------------------------------- timeline

    def build_timeline(self, incident: Incident, db: Session) -> list[dict[str, Any]]:
        """Merged chronological view: creation, alerts, events, transitions."""
        entries: list[dict[str, Any]] = []

        history = (
            db.execute(
                select(IncidentStateHistory)
                .where(IncidentStateHistory.incident_id == incident.id)
                .order_by(IncidentStateHistory.changed_at.asc())
            )
            .scalars()
            .all()
        )
        for row in history:
            entries.append(
                {
                    "type": "state_change",
                    "timestamp": as_utc(row.changed_at).isoformat(),
                    "from_status": row.from_status,
                    "to_status": row.to_status,
                    "actor": row.changed_by,
                    "note": row.note,
                }
            )

        alerts = (
            db.execute(select(Alert).where(Alert.incident_id == incident.id))
            .scalars()
            .all()
        )
        for alert in alerts:
            entries.append(
                {
                    "type": "alert",
                    "timestamp": as_utc(
                        alert.first_seen_at or alert.created_at
                    ).isoformat(),
                    "alert_id": alert.id,
                    "title": alert.title,
                    "severity": alert.severity,
                    "event_type": alert.event_type,
                    "event_count": alert.event_count,
                    "recovery": alert.event_type in RECOVERY_EVENT_TYPES,
                }
            )

        event_links = (
            db.execute(
                select(IncidentEvent, SyslogEvent)
                .join(SyslogEvent, IncidentEvent.event_id == SyslogEvent.id)
                .where(IncidentEvent.incident_id == incident.id)
            )
            .all()
        )
        for _link, event in event_links:
            entries.append(
                {
                    "type": "event",
                    "timestamp": as_utc(event.received_at).isoformat(),
                    "event_id": event.id,
                    "event_type": event.event_type_code,
                    "hostname": event.hostname,
                    "message": event.message,
                }
            )

        entries.sort(key=lambda entry: entry["timestamp"])
        return entries


# ---------------------------------------------------------------------------
# Serialization + process-wide default engine.
# ---------------------------------------------------------------------------

def _serialize_incident(incident: Incident) -> dict[str, Any]:
    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    return {
        "id": incident.id,
        "correlation_key": incident.correlation_key,
        "title": incident.title,
        "status": incident.status,
        "severity": incident.severity,
        "score": incident.score,
        "category": incident.category,
        "device_id": incident.device_id,
        "affected_devices": incident.affected_devices or [],
        "alert_count": incident.alert_count,
        "root_cause": incident.root_cause,
        "root_cause_candidates": incident.root_cause_candidates or [],
        "confidence": incident.confidence,
        "first_seen_at": iso(incident.first_seen_at),
        "last_seen_at": iso(incident.last_seen_at),
        "acknowledged_at": iso(incident.acknowledged_at),
        "acknowledged_by": incident.acknowledged_by,
        "resolved_at": iso(incident.resolved_at),
        "closed_at": iso(incident.closed_at),
        "created_at": iso(incident.created_at),
        "updated_at": iso(incident.updated_at),
    }


def _serialize_payload(incident: Incident, action: str) -> dict[str, Any]:
    return {
        "type": "incident",
        "action": action,  # "created" | "updated" | "status_changed"
        "incident": _serialize_incident(incident),
    }


_default_engine: CorrelationEngine | None = None
_default_lock = threading.Lock()


def get_correlation_engine() -> CorrelationEngine:
    """Return (creating once) the default engine built from settings."""
    global _default_engine
    with _default_lock:
        if _default_engine is None:
            _default_engine = CorrelationEngine()
            logger.info(
                "Correlation engine ready: %s rules, window=%ss, enabled=%s",
                len(_default_engine.rules),
                _default_engine.config.time_window_seconds,
                _default_engine.config.enabled,
            )
    return _default_engine


def reset_correlation_engine() -> None:
    """Drop the cached default engine (tests rebuild it from settings)."""
    global _default_engine
    with _default_lock:
        _default_engine = None
