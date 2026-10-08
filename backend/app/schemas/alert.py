"""Response/request schemas for alert endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.event import DeviceOut, EventOut


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    severity: str
    status: str
    rule_name: str | None = None
    dedupe_key: str
    title: str
    message: str | None = None
    context: dict | None = None
    event_count: int
    device_id: int | None = None
    event_id: int | None = None
    incident_id: int | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AlertListResponse(BaseModel):
    items: list[AlertOut]
    total: int
    limit: int
    offset: int


class AlertDetailResponse(BaseModel):
    alert: AlertOut
    device: DeviceOut | None = None
    event: EventOut | None = None


class AlertActionRequest(BaseModel):
    """Optional payload for acknowledge/resolve."""

    actor: str | None = None
