"""Response/request schemas for incident endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.alert import AlertOut


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    correlation_key: str
    title: str
    status: str
    severity: str
    score: float
    category: str | None = None
    device_id: int | None = None
    affected_devices: list[dict[str, Any]] = []
    alert_count: int
    root_cause: str | None = None
    root_cause_candidates: list[dict[str, Any]] = []
    confidence: float | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    @field_validator("root_cause_candidates", mode="before")
    @classmethod
    def normalize_root_cause_candidates(cls, value):
        if value is None:
            return []
        return value
       


class IncidentListResponse(BaseModel):
    items: list[IncidentOut]
    total: int
    limit: int
    offset: int


class IncidentDetailResponse(BaseModel):
    incident: IncidentOut
    alerts: list[AlertOut] = []


class TimelineEntry(BaseModel):
    type: str  # state_change | alert | event
    timestamp: str
    # state_change fields
    from_status: str | None = None
    to_status: str | None = None
    actor: str | None = None
    note: str | None = None
    # alert fields
    alert_id: int | None = None
    title: str | None = None
    severity: str | None = None
    event_type: str | None = None
    event_count: int | None = None
    recovery: bool | None = None
    # event fields
    event_id: int | None = None
    hostname: str | None = None
    message: str | None = None


class IncidentTimelineResponse(BaseModel):
    incident_id: int
    entries: list[TimelineEntry]


class IncidentActionRequest(BaseModel):
    """Optional payload for acknowledge/resolve/close."""

    actor: str | None = None
    note: str | None = None
