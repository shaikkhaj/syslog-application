"""Phase 1 database schema.

Tables created in Phase 1:
  * event_types   — catalog of detectable event categories (seeded)
  * devices       — auto-registered network devices (by source IP)
  * interfaces    — interfaces discovered inside syslog payloads
  * syslog_events — normalized syslog events
  * incidents     — reserved for the correlation engine (later phases)
  * alerts        — reserved for the alerting engine (later phases)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# JSON that upgrades to JSONB on PostgreSQL but stays portable on SQLite (tests).
JSONField = JSON().with_variant(JSONB(), "postgresql")

# 64-bit primary keys on PostgreSQL, native AUTOINCREMENT on SQLite.
PK = BigInteger().with_variant(Integer, "sqlite")


def utcnow() -> datetime:
    """Timezone-aware current time in UTC."""
    return datetime.now(timezone.utc)


class EventType(Base):
    __tablename__ = "event_types"

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Regex fragments (IGNORECASE) matched against the normalized message.
    patterns: Mapped[list | None] = mapped_column(JSONField, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("ip_address", name="uq_devices_ip_address"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Interface(Base):
    __tablename__ = "interfaces"
    __table_args__ = (
        UniqueConstraint("device_id", "name", name="uq_interfaces_device_name"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    if_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    oper_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Incident(Base):
    """Reserved for the correlation / RCA engine (later phases)."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Alert(Base):
    """Alerts raised by the detection engine (Phase 2).

    Alerts are deduplicated through ``dedupe_key``: while an alert with the
    same key is still open (not resolved), repeated findings coalesce into it
    (``event_count``/``last_seen_at`` are updated instead of inserting rows).
    ``incident_id`` stays reserved for the Phase 3 correlation engine.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_event_type", "event_type"),
        Index("ix_alerts_dedupe_key", "dedupe_key"),
        Index("ix_alerts_last_seen", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("syslog_events.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    rule_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONField, nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SyslogEvent(Base):
    __tablename__ = "syslog_events"
    __table_args__ = (
        Index("ix_syslog_events_received_at", "received_at"),
        Index("ix_syslog_events_device_received", "device_id", "received_at"),
        Index("ix_syslog_events_severity", "severity"),
        Index("ix_syslog_events_hostname", "hostname"),
        Index("ix_syslog_events_source_ip", "source_ip"),
        Index("ix_syslog_events_type", "event_type_id"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rfc: Mapped[str] = mapped_column(String(16), nullable=False, default="raw")
    facility: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    procid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    msgid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    interface_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("event_types.id", ondelete="SET NULL"), nullable=True
    )
    event_type_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict | None] = mapped_column(JSONField, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
