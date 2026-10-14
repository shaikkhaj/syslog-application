"""Schemas for the topology graph and device/link CRUD (Phase 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeviceType = Literal["router", "switch", "firewall", "server"]
DeviceStatus = Literal["active", "offline", "maintenance"]
LinkStatus = Literal["up", "down"]


class TopologyNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hostname: str | None = None
    ip_address: str
    vendor: str
    device_type: str = "router"
    status: str
    last_seen_at: datetime
    # Highlighting derived from open alerts / active incidents:
    affected: bool = False
    open_alert_count: int = 0
    open_incident_count: int = 0
    max_severity: str | None = None


class TopologyLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_device_id: int
    source_interface: str
    target_device_id: int
    target_interface: str
    status: str
    affected: bool = False
    max_severity: str | None = None
    created_at: datetime
    updated_at: datetime


class TopologyResponse(BaseModel):
    nodes: list[TopologyNodeOut]
    links: list[TopologyLinkOut]


class DeviceCreate(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    ip_address: str = Field(
        min_length=3,
        max_length=45,
        pattern=r"^([0-9]{1,3}\.){3}[0-9]{1,3}$|^[0-9a-fA-F:]+$",
    )
    device_type: DeviceType = "router"
    status: DeviceStatus = "active"
    vendor: str = Field(default="unknown", max_length=64)


class DeviceUpdate(BaseModel):
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    device_type: DeviceType | None = None
    status: DeviceStatus | None = None
    vendor: str | None = Field(default=None, min_length=1, max_length=64)


class LinkCreate(BaseModel):
    source_device_id: int
    source_interface: str = Field(min_length=1, max_length=128)
    target_device_id: int
    target_interface: str = Field(min_length=1, max_length=128)
    status: LinkStatus = "up"


class LinkUpdate(BaseModel):
    source_interface: str | None = Field(default=None, min_length=1, max_length=128)
    target_interface: str | None = Field(default=None, min_length=1, max_length=128)
    status: LinkStatus | None = None
