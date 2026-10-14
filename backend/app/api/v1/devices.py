"""Device inventory discovered from syslog traffic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import (
    Alert,
    Device,
    EventType,
    Incident,
    Interface,
    SyslogEvent,
    TopologyLink,
)
from app.schemas.event import DeviceListResponse, DeviceOut, EventTypeOut
from app.schemas.topology import DeviceCreate, DeviceUpdate

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


# ---------------------------------------------------------------------------
# Device CRUD (Phase 4)
# ---------------------------------------------------------------------------

def _device_out(db: Session, device: Device) -> DeviceOut:
    count = db.execute(
        select(func.count())
        .select_from(SyslogEvent)
        .where(SyslogEvent.device_id == device.id)
    ).scalar_one()
    return DeviceOut(
        id=device.id,
        hostname=device.hostname,
        ip_address=device.ip_address,
        vendor=device.vendor,
        device_type=device.device_type or "router",
        status=device.status,
        first_seen_at=device.first_seen_at,
        last_seen_at=device.last_seen_at,
        event_count=int(count),
    )


@router.post(
    "/devices",
    response_model=DeviceOut,
    status_code=201,
    summary="Add a topology device",
)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)) -> DeviceOut:
    if db.execute(
        select(Device).where(Device.ip_address == payload.ip_address)
    ).scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail=f"Device with IP {payload.ip_address} already exists"
        )
    device = Device(
        hostname=payload.hostname,
        ip_address=payload.ip_address,
        vendor=payload.vendor,
        device_type=payload.device_type,
        status=payload.status,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return _device_out(db, device)


@router.patch("/devices/{device_id}", response_model=DeviceOut, summary="Edit a device")
def update_device(
    device_id: int, payload: DeviceUpdate, db: Session = Depends(get_db)
) -> DeviceOut:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(device, key, value)
    db.commit()
    db.refresh(device)
    return _device_out(db, device)


@router.delete("/devices/{device_id}", status_code=204, summary="Delete a device")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    # Explicit cleanup: SQLite does not enforce ON DELETE side effects.
    db.execute(update(Alert).where(Alert.device_id == device_id).values(device_id=None))
    db.execute(
        update(Incident).where(Incident.device_id == device_id).values(device_id=None)
    )
    db.execute(delete(TopologyLink).where(
        (TopologyLink.source_device_id == device_id)
        | (TopologyLink.target_device_id == device_id)
    ))
    db.execute(delete(Interface).where(Interface.device_id == device_id))
    db.delete(device)
    db.commit()


@router.get(
    "/event-types",
    response_model=list[EventTypeOut],
    summary="List the event type catalog",
)
def list_event_types(db: Session = Depends(get_db)) -> list[EventType]:
    return list(db.execute(select(EventType).order_by(EventType.code)).scalars())
