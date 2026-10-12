"""Incident API: list, detail, lifecycle actions and timeline."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.correlation.engine import (
    _serialize_payload as serialize_incident_payload,
)
from app.correlation.engine import get_correlation_engine
from app.correlation.types import IncidentSeverity, IncidentStatus
from app.db.session import get_db
from app.models.models import Alert, Incident
from app.realtime.broadcaster import alert_broadcaster
from app.schemas.alert import AlertOut
from app.schemas.incident import (
    IncidentActionRequest,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentOut,
    IncidentTimelineResponse,
    TimelineEntry,
)

router = APIRouter(tags=["incidents"])

_STATUS_PATTERN = "^(OPEN|INVESTIGATING|ACKNOWLEDGED|RESOLVED|CLOSED)$"
_SEVERITY_PATTERN = "^(LOW|MEDIUM|HIGH|CRITICAL)$"


def _load_incident(incident_id: int, db: Session) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


def _transition(
    incident: Incident,
    to_status: IncidentStatus,
    db: Session,
    payload: IncidentActionRequest | None,
) -> Incident:
    engine = get_correlation_engine()
    try:
        engine.transition_status(
            incident,
            to_status,
            db,
            actor=(payload.actor if payload else None) or "api-user",
            note=payload.note if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    alert_broadcaster.emit(serialize_incident_payload(incident, "status_changed"))
    return incident


@router.get(
    "/incidents",
    response_model=IncidentListResponse,
    summary="List incidents with filtering",
)
def list_incidents(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, pattern=_STATUS_PATTERN),
    severity: Optional[str] = Query(None, pattern=_SEVERITY_PATTERN),
    category: Optional[str] = Query(None),
    device_id: Optional[int] = Query(None, ge=1),
    min_score: Optional[float] = Query(None, ge=0),
    q: Optional[str] = Query(None, min_length=1, max_length=200),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
) -> IncidentListResponse:
    filters = []
    if status:
        filters.append(Incident.status == status)
    if severity:
        filters.append(Incident.severity == severity)
    if category:
        filters.append(Incident.category == category)
    if device_id:
        filters.append(Incident.device_id == device_id)
    if min_score is not None:
        filters.append(Incident.score >= min_score)
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(Incident.title.ilike(pattern), Incident.root_cause.ilike(pattern))
        )
    if since is not None:
        filters.append(Incident.last_seen_at >= since)
    if until is not None:
        filters.append(Incident.last_seen_at <= until)

    total = db.execute(
        select(func.count()).select_from(Incident).where(*filters)
    ).scalar_one()
    rows = (
        db.execute(
            select(Incident)
            .where(*filters)
            .order_by(Incident.last_seen_at.desc(), Incident.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return IncidentListResponse(items=rows, total=total, limit=limit, offset=offset)


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentDetailResponse,
    summary="Incident details with related alerts",
)
def get_incident(
    incident_id: int, db: Session = Depends(get_db)
) -> IncidentDetailResponse:
    incident = _load_incident(incident_id, db)
    alerts = (
        db.execute(
            select(Alert)
            .where(Alert.incident_id == incident.id)
            .order_by(Alert.first_seen_at.asc())
        )
        .scalars()
        .all()
    )
    return IncidentDetailResponse(incident=incident, alerts=alerts)


@router.post(
    "/incidents/{incident_id}/acknowledge",
    response_model=IncidentOut,
    summary="Acknowledge an incident",
)
def acknowledge_incident(
    incident_id: int,
    payload: IncidentActionRequest | None = None,
    db: Session = Depends(get_db),
) -> Incident:
    incident = _load_incident(incident_id, db)
    if incident.status == IncidentStatus.ACKNOWLEDGED.value:
        return incident  # idempotent
    return _transition(incident, IncidentStatus.ACKNOWLEDGED, db, payload)


@router.post(
    "/incidents/{incident_id}/resolve",
    response_model=IncidentOut,
    summary="Resolve an incident",
)
def resolve_incident(
    incident_id: int,
    payload: IncidentActionRequest | None = None,
    db: Session = Depends(get_db),
) -> Incident:
    incident = _load_incident(incident_id, db)
    return _transition(incident, IncidentStatus.RESOLVED, db, payload)


@router.post(
    "/incidents/{incident_id}/close",
    response_model=IncidentOut,
    summary="Close a resolved incident",
)
def close_incident(
    incident_id: int,
    payload: IncidentActionRequest | None = None,
    db: Session = Depends(get_db),
) -> Incident:
    incident = _load_incident(incident_id, db)
    return _transition(incident, IncidentStatus.CLOSED, db, payload)


@router.get(
    "/incidents/{incident_id}/timeline",
    response_model=IncidentTimelineResponse,
    summary="Chronological incident timeline",
)
def incident_timeline(
    incident_id: int, db: Session = Depends(get_db)
) -> IncidentTimelineResponse:
    incident = _load_incident(incident_id, db)
    engine = get_correlation_engine()
    entries = engine.build_timeline(incident, db)
    return IncidentTimelineResponse(
        incident_id=incident.id,
        entries=[TimelineEntry(**entry) for entry in entries],
    )
