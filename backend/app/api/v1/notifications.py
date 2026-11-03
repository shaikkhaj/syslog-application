"""Notification API: history, read-state, settings and escalation (Phase 7)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.notification import Notification
from app.realtime.broadcaster import alert_broadcaster
from app.schemas.notification import (
    EscalationTriggerResponse,
    NotificationListResponse,
    NotificationOut,
    NotificationReadAllRequest,
    NotificationReadRequest,
    NotificationSettingsOut,
    NotificationSettingsUpdate,
)
from app.services.escalation_service import (
    escalate_unacknowledged_critical_incidents,
)
from app.services.notification_service import (
    get_notification_settings,
    get_unread_count,
    list_notifications,
    mark_all_as_read,
    mark_as_read,
    update_notification_settings,
)

router = APIRouter(tags=["notifications"])


def _publish_notification(notification: Notification, action: str) -> None:
    alert_broadcaster.emit(
        {
            "type": "notification",
            "action": action,
            "notification": {
                "id": notification.id,
                "type": notification.type,
                "severity": notification.severity,
                "title": notification.title,
                "related_alert_id": notification.related_alert_id,
                "related_incident_id": notification.related_incident_id,
                "is_read": notification.is_read,
                "created_at": notification.created_at.isoformat()
                if notification.created_at
                else None,
            },
        }
    )


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    summary="List notifications with optional unread-only filter",
)
def list_notifications_api(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    type: Optional[str] = Query(None, description="alert | incident | escalation"),
    severity: Optional[str] = Query(None, description="INFO | LOW | MEDIUM | HIGH | CRITICAL"),
) -> NotificationListResponse:
    rows, total, unread_count = list_notifications(
        db,
        unread_only=unread_only,
        type=type,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=rows, total=total, limit=limit, offset=offset,
        unread_count=unread_count,
    )


@router.get(
    "/notifications/unread-count",
    response_model=dict,
    summary="Return the number of unread notifications",
)
def unread_count_api(db: Session = Depends(get_db)) -> dict:
    return {"unread_count": get_unread_count(db)}


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationOut,
    summary="Mark a notification as read",
)
def mark_notification_read(
    notification_id: int,
    payload: NotificationReadRequest | None = None,
    db: Session = Depends(get_db),
) -> Notification:
    notification = mark_as_read(
        db, notification_id, actor=payload.actor if payload else None
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.commit()
    _publish_notification(notification, "read")
    return notification


@router.post(
    "/notifications/read-all",
    response_model=dict,
    summary="Mark all unread notifications as read",
)
def mark_all_notifications_read(
    payload: NotificationReadAllRequest | None = None,
    db: Session = Depends(get_db),
) -> dict:
    count = mark_all_as_read(
        db, actor=payload.actor if payload else None
    )
    db.commit()
    return {"marked_read": count}


@router.get(
    "/notifications/settings",
    response_model=NotificationSettingsOut,
    summary="Get notification settings",
)
def get_settings_api(db: Session = Depends(get_db)) -> NotificationSettingsOut:
    settings = get_notification_settings(db)
    db.commit()
    return settings


@router.patch(
    "/notifications/settings",
    response_model=NotificationSettingsOut,
    summary="Update notification settings",
)
def update_settings_api(
    payload: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
) -> NotificationSettingsOut:
    settings = update_notification_settings(
        db, payload.model_dump(exclude_unset=True)
    )
    db.commit()
    return settings


@router.post(
    "/notifications/escalate",
    response_model=EscalationTriggerResponse,
    summary="Trigger an escalation check for unacknowledged critical incidents",
)
def escalate_api(db: Session = Depends(get_db)) -> EscalationTriggerResponse:
    created = escalate_unacknowledged_critical_incidents(db)
    return EscalationTriggerResponse(
        escalated=len(created),
        message=(
            str(len(created)) + " escalation notification(s) created"
            if created
            else "No incidents required escalation"
        ),
    )

