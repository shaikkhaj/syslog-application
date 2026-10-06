"""Read-only queries over ingested syslog events."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import SyslogEvent
from app.schemas.event import EventListResponse, EventOut

router = APIRouter(tags=["events"])


@router.get(
    "/events",
    response_model=EventListResponse,
    summary="List syslog events with filtering",
)
def list_events(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    severity: Optional[int] = Query(None, ge=0, le=7, description="Exact syslog severity (0-7)"),
    hostname: Optional[str] = Query(None, description="Exact hostname"),
    device_ip: Optional[str] = Query(None, description="Exact source IP"),
    event_type: Optional[str] = Query(None, description="Event type code"),
    rfc: Optional[str] = Query(None, description="RFC variant: 3164 | 5424 | raw"),
    q: Optional[str] = Query(None, min_length=1, max_length=200, description="Search message/hostname"),
    since: Optional[datetime] = Query(None, description="received_at >= since"),
    until: Optional[datetime] = Query(None, description="received_at <= until"),
) -> EventListResponse:
    filters = []
    if severity is not None:
        filters.append(SyslogEvent.severity == severity)
    if hostname:
        filters.append(SyslogEvent.hostname == hostname)
    if device_ip:
        filters.append(SyslogEvent.source_ip == device_ip)
    if event_type:
        filters.append(SyslogEvent.event_type_code == event_type)
    if rfc:
        filters.append(SyslogEvent.rfc == rfc)
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(
                SyslogEvent.message.ilike(pattern),
                SyslogEvent.hostname.ilike(pattern),
                SyslogEvent.raw_message.ilike(pattern),
            )
        )
    if since is not None:
        filters.append(SyslogEvent.received_at >= since)
    if until is not None:
        filters.append(SyslogEvent.received_at <= until)

    total = db.execute(
        select(func.count()).select_from(SyslogEvent).where(*filters)
    ).scalar_one()
    rows = (
        db.execute(
            select(SyslogEvent)
            .where(*filters)
            .order_by(SyslogEvent.received_at.desc(), SyslogEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return EventListResponse(items=rows, total=total, limit=limit, offset=offset)


@router.get(
    "/events/{event_id}",
    response_model=EventOut,
    summary="Get one syslog event by id",
)
def get_event(event_id: int, db: Session = Depends(get_db)) -> SyslogEvent:
    event = db.get(SyslogEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
