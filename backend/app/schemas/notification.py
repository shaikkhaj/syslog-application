"""Response/request schemas for notification endpoints (Phase 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str  # alert | incident | escalation
    severity: str  # INFO | LOW | MEDIUM | HIGH | CRITICAL
    title: str
    message: str | None = None
    dedupe_key: str
    related_alert_id: int | None = None
    related_incident_id: int | None = None
    channel: str  # in_app | email
    status: str  # pending | sent | failed
    error_message: str | None = None
    retry_count: int
    sent_at: datetime | None = None
    is_read: bool
    read_at: datetime | None = None
    read_by: str | None = None
    context: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]
    total: int
    limit: int
    offset: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class NotificationReadRequest(BaseModel):
    actor: str | None = None


class NotificationReadAllRequest(BaseModel):
    actor: str | None = None


class NotificationSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    min_severity: str
    escalation_delay_minutes: int
    email_enabled: bool
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    email_from: str | None = None
    email_to: str | None = None
    updated_at: datetime


class NotificationSettingsUpdate(BaseModel):
    min_severity: str | None = Field(
        None, pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$"
    )
    escalation_delay_minutes: int | None = Field(None, ge=0)
    email_enabled: bool | None = None
    smtp_host: str | None = None
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    email_to: str | None = None


class EscalationTriggerResponse(BaseModel):
    escalated: int
    message: str
