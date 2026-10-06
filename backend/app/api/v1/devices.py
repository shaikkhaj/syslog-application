"""Device inventory discovered from syslog traffic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Device, EventType, SyslogEvent
from app.schemas.event import DeviceListResponse, DeviceOut, EventTypeOut

router = APIRouter(tags=["devices"])


@router.get(
    "/devices",
    response_model=DeviceListResponse,
    summary="List discovered devices",
)
def list_devices(
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> DeviceListResponse:
    counts = (
        select(
            SyslogEvent.device_id.label("device_id"),
            func.count().label("event_count"),
        )
        .group_by(SyslogEvent.device_id)
        .subquery()
    )
    total = db.execute(select(func.count()).select_from(Device)).scalar_one()
    rows = db.execute(
        select(Device, func.coalesce(counts.c.event_count, 0))
        .outerjoin(counts, counts.c.device_id == Device.id)
        .order_by(Device.last_seen_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        DeviceOut(
            id=device.id,
            hostname=device.hostname,
            ip_address=device.ip_address,
            vendor=device.vendor,
            status=device.status,
            first_seen_at=device.first_seen_at,
            last_seen_at=device.last_seen_at,
            event_count=int(event_count),
        )
        for device, event_count in rows
    ]
    return DeviceListResponse(items=items, total=total)


@router.get(
    "/event-types",
    response_model=list[EventTypeOut],
    summary="List the event type catalog",
)
def list_event_types(db: Session = Depends(get_db)) -> list[EventType]:
    return list(db.execute(select(EventType).order_by(EventType.code)).scalars())
