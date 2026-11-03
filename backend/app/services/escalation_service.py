"""Incident escalation service (Phase 7).

Escalates unacknowledged critical incidents after a configurable delay.
Escalation is idempotent (one escalation notification per incident) and
stops when the incident is acknowledged, resolved or closed.

The escalation check is designed to be invoked both:
  * periodically by a background asyncio task in production (see main.py),
  * directly from unit tests and via an on-demand API endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.correlation.types import IncidentSeverity, IncidentStatus
from app.models.models import Incident
from app.models.notification import Notification
from app.services.notification_service import (
    create_notification,
    get_notification_settings,
)

logger = logging.getLogger(__name__)


def escalate_unacknowledged_critical_incidents(
    db: Session,
) -> list[Notification]:
    """Escalate critical incidents that are unacknowledged past the delay.

    Returns the list of newly created escalation notifications. Idempotent:
    an incident that already has an escalation notification is skipped.
    Escalation stops for incidents that are acknowledged, resolved or closed.
    """
    settings = get_notification_settings(db)
    delay = timedelta(minutes=settings.escalation_delay_minutes)
    cutoff = datetime.now(timezone.utc) - delay

    incidents = (
        db.execute(
            select(Incident).where(
                Incident.severity == IncidentSeverity.CRITICAL.value,
                Incident.status.in_(
                    [
                        IncidentStatus.OPEN.value,
                        IncidentStatus.INVESTIGATING.value,
                    ]
                ),
                Incident.created_at <= cutoff,
                Incident.acknowledged_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    created: list[Notification] = []
    for incident in incidents:
        notification = create_notification(
            db,
            type="escalation",
            severity=IncidentSeverity.CRITICAL.value,
            title="Escalation: unacknowledged critical incident",
            message=(
                "Critical incident '"
                + incident.title
                + "' (id="
                + str(incident.id)
                + ") has been unacknowledged for more than "
                + str(settings.escalation_delay_minutes)
                + " minutes."
            ),
            related_incident_id=incident.id,
            context={
                "incident_id": incident.id,
                "correlation_key": incident.correlation_key,
                "escalation_reason": "unacknowledged_critical",
            },
        )
        if notification is not None:
            created.append(notification)

    if created:
        db.commit()

    return created

