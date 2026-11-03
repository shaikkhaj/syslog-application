"""Alert persistence with dedupe/coalescing semantics.

While an alert with the same ``dedupe_key`` is open (not resolved), new
findings coalesce into it: ``event_count``/``last_seen_at`` are updated and
the severity only ever escalates. Once resolved, the next finding opens a
fresh alert.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detection.types import AlertSeverity, AlertStatus, DetectionResult
from app.models.models import Alert, SyslogEvent
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)


def raise_alert(
    db: Session,
    result: DetectionResult,
    event: SyslogEvent,
) -> tuple[Alert, bool]:
    """Persist a detection finding.

    Returns:
        ``(alert, created)`` — ``created`` is False when the finding was
        coalesced into an existing open alert.
    """
    now = datetime.now(timezone.utc)
    existing = db.execute(
        select(Alert)
        .where(
            Alert.dedupe_key == result.dedupe_key,
            Alert.status != AlertStatus.RESOLVED.value,
        )
        .order_by(Alert.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if existing is not None:
        existing.last_seen_at = now
        existing.event_count += 1
        existing.event_id = event.id
        existing.message = result.message or existing.message
        existing.context = result.context or existing.context
        if AlertSeverity.order(result.severity) > AlertSeverity.order(
            existing.severity
        ):
            existing.severity = result.severity.value
            logger.info(
                "Alert %s severity escalated to %s",
                existing.id,
                existing.severity,
            )
        return existing, False

    alert = Alert(
        event_type=result.event_type.value,
        severity=result.severity.value,
        status=AlertStatus.NEW.value,
        rule_name=result.rule_name or None,
        dedupe_key=result.dedupe_key,
        title=result.title,
        message=result.message,
        context=result.context or None,
        event_count=1,
        device_id=event.device_id,
        event_id=event.id,
        first_seen_at=event.received_at or now,
        last_seen_at=now,
    )
    db.add(alert)
    db.flush()  # assigns the id before commit/broadcast
    logger.info(
        "Alert raised: [%s] %s (%s)",
        alert.severity,
        alert.title,
        alert.event_type,
    )
    # Fire an in-app notification for new alerts that meet the severity threshold.
    create_notification(
        db,
        type="alert",
        severity=alert.severity,
        title=alert.title,
        message=alert.message,
        related_alert_id=alert.id,
        context={"rule_name": alert.rule_name, "event_count": alert.event_count},
    )
    return alert, True
