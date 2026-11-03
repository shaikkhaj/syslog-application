"""Notification and notification-settings models (Phase 7).

Tables:
  * notifications        — persistent notification history (in-app first,
                            optional email/external delivery).
  * notification_settings — configurable severity threshold, escalation
                            delay and email delivery settings (singleton).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.models import JSONField, PK, utcnow


class Notification(Base):
    """A single notification raised for an alert, incident or escalation.

    ``dedupe_key`` prevents duplicate notifications for repeated events that
    belong to the same existing alert/incident (e.g. ``alert:42``,
    ``incident:7``, ``escalation:incident:7``).
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_related_alert", "related_alert_id"),
        Index("ix_notifications_related_incident", "related_incident_id"),
        Index("ix_notifications_status", "status"),
        Index("ix_notifications_created_at", "created_at"),
        Index("ix_notifications_read", "is_read"),
        CheckConstraint(
            "severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_notifications_severity",
        ),
        CheckConstraint(
            "status IN ('pending','sent','failed')",
            name="ck_notifications_status",
        ),
        CheckConstraint(
            "type IN ('alert','incident','escalation')",
            name="ck_notifications_type",
        ),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    # alert | incident | escalation
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    # INFO | LOW | MEDIUM | HIGH | CRITICAL
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    related_alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    related_incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Delivery
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="in_app"
    )
    # in_app | email
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="sent"
    )
    # pending | sent | failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Read state
    is_read: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Context (extra payload, e.g. rule name, event count)
    context: Mapped[dict | None] = mapped_column(JSONField, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class NotificationSettings(Base):
    """Singleton configuration for notification behaviour.

    Only one row is expected (id == 1). Updated via the settings API;
    sensible defaults are applied when the row is absent.
    """

    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    # Minimum severity that triggers a notification (INFO < LOW < MEDIUM < HIGH < CRITICAL).
    min_severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="HIGH"
    )
    # Minutes an unacknowledged critical incident must wait before escalation.
    escalation_delay_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15
    )
    # Email delivery (optional, off by default — no paid API required).
    email_enabled: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0
    )
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # smtp_password is intentionally stored in plain text only for local
    # development; production deployments should inject it via env/secret mgr.
    smtp_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

