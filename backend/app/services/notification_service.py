"""Notification business logic (Phase 7)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.orm import Session

from app.models.notification import (
    Notification,
    NotificationSettings,
)

_SEVERITY_ORDER = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _severity_rank(severity: str) -> int:
    try:
        return _SEVERITY_ORDER.index(severity.upper())
    except ValueError:
        return 0


def _meets_threshold(severity: str, min_severity: str) -> bool:
    return _severity_rank(severity) >= _severity_rank(min_severity)


def get_notification_settings(db: Session) -> NotificationSettings:
    settings = db.execute(select(NotificationSettings).limit(1)).scalar_one_or_none()
    if settings is None:
        settings = NotificationSettings()
        db.add(settings)
        db.flush()
    return settings


def update_notification_settings(db: Session, payload: dict[str, Any]) -> NotificationSettings:
    settings = get_notification_settings(db)
    for field, value in payload.items():
        if hasattr(settings, field) and value is not None:
            setattr(settings, field, value)
    db.add(settings)
    db.flush()
    return settings


def _dedupe_key_for(kind: str, related_id: int | None, alert_id: int | None = None) -> str:
    if kind == "escalation" and related_id is not None:
        return f"escalation:incident:{related_id}"
    if kind == "incident" and related_id is not None:
        return f"incident:{related_id}"
    if kind == "alert" and alert_id is not None:
        return f"alert:{alert_id}"
    return f"{kind}:{related_id}"


def create_notification(
    db: Session,
    *,
    type: str,
    severity: str,
    title: str,
    message: str | None = None,
    related_alert_id: int | None = None,
    related_incident_id: int | None = None,
    channel: str = "in_app",
    context: dict[str, Any] | None = None,
) -> Notification | None:
    """Create a notification unless one already exists for the same target."""
    settings = get_notification_settings(db)
    if not _meets_threshold(severity, settings.min_severity):
        return None
    if type == "alert" and related_alert_id is not None:
        dedupe_key = _dedupe_key_for("alert", None, alert_id=related_alert_id)
    elif type == "incident" and related_incident_id is not None:
        dedupe_key = _dedupe_key_for("incident", related_incident_id)
    elif type == "escalation" and related_incident_id is not None:
        dedupe_key = _dedupe_key_for("escalation", related_incident_id)
    else:
        dedupe_key = _dedupe_key_for(type, related_incident_id)
    existing = db.execute(select(Notification).where(Notification.dedupe_key == dedupe_key)).scalar_one_or_none()
    if existing is not None:
        return existing
    notification = Notification(
        type=type, severity=severity, title=title, message=message,
        dedupe_key=dedupe_key, related_alert_id=related_alert_id,
        related_incident_id=related_incident_id, channel=channel, status="sent",
        context=context or None, sent_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    db.flush()
    return notification


def list_notifications(
    db: Session, *, unread_only: bool = False, type: str | None = None,
    severity: str | None = None, limit: int = 50, offset: int = 0,
) -> tuple[list[Notification], int, int]:
    filters = []
    if unread_only:
        filters.append(Notification.is_read == 0)
    if type:
        filters.append(Notification.type == type)
    if severity:
        filters.append(Notification.severity == severity)
    base = select(Notification).where(*filters)
    total = db.execute(select(func.count()).select_from(Notification).where(*filters)).scalar_one()
    unread_count = db.execute(select(func.count()).select_from(Notification).where(Notification.is_read == 0)).scalar_one()
    rows = db.execute(base.order_by(Notification.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return rows, total, unread_count


def get_unread_count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Notification).where(Notification.is_read == 0)).scalar_one()


def mark_as_read(db: Session, notification_id: int, actor: str | None = None) -> Notification | None:
    notification = db.get(Notification, notification_id)
    if notification is None:
        return None
    notification.is_read = 1
    notification.read_at = datetime.now(timezone.utc)
    notification.read_by = actor or "api-user"
    db.add(notification)
    db.flush()
    return notification


def mark_all_as_read(db: Session, actor: str | None = None) -> int:
    now = datetime.now(timezone.utc)
    result = db.execute(sa_update(Notification).where(Notification.is_read == 0).values(is_read=1, read_at=now, read_by=actor or "api-user"))
    db.flush()
    return result.rowcount or 0

