"""Alert API: list, filter, detail, acknowledge and resolve."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.detection.types import AlertSeverity, AlertStatus
from app.models.models import Alert, Device, SyslogEvent
from app.realtime.broadcaster import alert_broadcaster
from app.schemas.alert import (
    AlertActionRequest,
    AlertDetailResponse,
    AlertListResponse,
    AlertOut,
)
from app.schemas.event import DeviceOut, EventOut

router = APIRouter(tags=["alerts"])


def _publish(alert: Alert, action: str) -> None:
    """Push a manual status change to WebSocket subscribers."""
    alert_broadcaster.emit(
        {
            "type": "alert",
            "action": action,
            "alert": {
                "id": alert.id,
                "event_type": alert.event_type,
                "severity": alert.severity,
                "status": alert.status,
                "title": alert.title,
                "event_count": alert.event_count,
                "device_id": alert.device_id,
                "acknowledged_by": alert.acknowledged_by,
                "last_seen_at": alert.last_seen_at.isoformat()
                if alert.last_seen_at
                else None,
            },
        }
    )


@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="List alerts with filtering",
)
def list_alerts(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, pattern="^(new|acknowledged|resolved)$"),
    severity: Optional[str] = Query(None, pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$"),
    event_type: Optional[str] = Query(None, description="Event type code"),
    device_id: Optional[int] = Query(None, ge=1),
    q: Optional[str] = Query(None, min_length=1, max_length=200),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
) -> AlertListResponse:
    filters = []
    if status:
        filters.append(Alert.status == status)
    if severity:
        filters.append(Alert.severity == severity)
    if event_type:
        filters.append(Alert.event_type == event_type)
    if device_id:
        filters.append(Alert.device_id == device_id)
    if q:
        pattern = f"%{q}%"
        filters.append(or_(Alert.title.ilike(pattern), Alert.message.ilike(pattern)))
    if since is not None:
        filters.append(Alert.last_seen_at >= since)
    if until is not None:
        filters.append(Alert.last_seen_at <= until)

    total = db.execute(select(func.count()).select_from(Alert).where(*filters)).scalar_one()
    rows = (
        db.execute(
            select(Alert)
            .where(*filters)
            .order_by(Alert.last_seen_at.desc(), Alert.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return AlertListResponse(items=rows, total=total, limit=limit, offset=offset)


@router.get(
    "/alerts/{alert_id}",
    response_model=AlertDetailResponse,
    summary="Alert details with device and triggering event",
)
def get_alert(alert_id: int, db: Session = Depends(get_db)) -> AlertDetailResponse:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    device = db.get(Device, alert.device_id) if alert.device_id else None
    event = db.get(SyslogEvent, alert.event_id) if alert.event_id else None
    return AlertDetailResponse(
        alert=alert,
        device=DeviceOut(
            id=device.id,
            hostname=device.hostname,
            ip_address=device.ip_address,
            vendor=device.vendor,
            status=device.status,
            first_seen_at=device.first_seen_at,
            last_seen_at=device.last_seen_at,
            event_count=0,
        )
        if device
        else None,
        event=EventOut.model_validate(event) if event else None,
    )


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertOut,
    summary="Acknowledge an alert",
)
def acknowledge_alert(
    alert_id: int,
    payload: AlertActionRequest | None = None,
    db: Session = Depends(get_db),
) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == AlertStatus.RESOLVED.value:
        raise HTTPException(status_code=409, detail="Alert is already resolved")

    alert.status = AlertStatus.ACKNOWLEDGED.value
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = (payload.actor if payload else None) or "api-user"
    db.commit()
    db.refresh(alert)
    _publish(alert, "updated")
    return alert


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertOut,
    summary="Resolve an alert",
)
def resolve_alert(
    alert_id: int,
    payload: AlertActionRequest | None = None,
    db: Session = Depends(get_db),
) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == AlertStatus.RESOLVED.value:
        raise HTTPException(status_code=409, detail="Alert is already resolved")

    alert.status = AlertStatus.RESOLVED.value
    alert.resolved_at = datetime.now(timezone.utc)
    if alert.acknowledged_at is None:
        alert.acknowledged_at = alert.resolved_at
        alert.acknowledged_by = (payload.actor if payload else None) or "api-user"
    db.commit()
    db.refresh(alert)
    _publish(alert, "updated")
    return alert
