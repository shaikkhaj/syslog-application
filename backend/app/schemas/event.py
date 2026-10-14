"""Response schemas for syslog events and devices."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    received_at: datetime
    timestamp: datetime | None = None
    source_ip: str
    device_id: int | None = None
    rfc: str
    facility: int | None = None
    severity: int | None = None
    severity_label: str | None = None
    hostname: str | None = None
    app_name: str | None = None
    procid: str | None = None
    msgid: str | None = None
    vendor: str
    interface_name: str | None = None
    event_type_code: str | None = None
    message: str
    raw_message: str
    structured_data: dict | None = None


class EventListResponse(BaseModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hostname: str | None = None
    ip_address: str
    vendor: str
    device_type: str | None = "router"
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    event_count: int = 0


class DeviceListResponse(BaseModel):
    items: list[DeviceOut]
    total: int


class EventTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    description: str | None = None
