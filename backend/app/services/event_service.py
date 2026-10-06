"""Persistence logic for ingested syslog events (device/interface upserts)."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import Device, Interface, SyslogEvent
from app.syslog.event_types import resolver
from app.syslog.normalize import NormalizedEvent, normalize
from app.syslog.parser import ParsedSyslog

logger = logging.getLogger(__name__)


def _upsert_device(db: Session, norm: NormalizedEvent, seen_at: datetime) -> Device:
    """Create or refresh the device record for the event's source IP.

    Pipeline workers run concurrently, so two workers can both fail to find
    a brand-new device and race to insert it. The loser catches the unique
    constraint violation, rolls back and re-reads the winner's row.
    """

    def find() -> Device | None:
        return db.execute(
            select(Device).where(Device.ip_address == norm.source_ip)
        ).scalar_one_or_none()

    device = find()
    if device is None:
        candidate = Device(
            ip_address=norm.source_ip,
            hostname=norm.hostname or norm.source_ip,
            vendor=norm.vendor,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        db.add(candidate)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            device = find()
            if device is None:  # pragma: no cover - unexpected constraint source
                raise
        else:
            logger.info(
                "Registered new device %s (%s) from %s",
                candidate.hostname,
                candidate.vendor,
                candidate.ip_address,
            )
            return candidate

    device.last_seen_at = seen_at
    if norm.hostname and device.hostname in (None, device.ip_address):
        device.hostname = norm.hostname
    if norm.vendor != "unknown" and device.vendor == "unknown":
        device.vendor = norm.vendor
    return device


def _upsert_interface(
    db: Session, device: Device, name: str, seen_at: datetime
) -> Interface:
    """Create or refresh an interface row discovered in the payload."""

    def find() -> Interface | None:
        return db.execute(
            select(Interface).where(
                Interface.device_id == device.id, Interface.name == name
            )
        ).scalar_one_or_none()

    interface = find()
    if interface is None:
        candidate = Interface(
            device_id=device.id,
            name=name,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        db.add(candidate)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            interface = find()
            if interface is None:  # pragma: no cover - unexpected constraint
                raise
        else:
            return candidate

    interface.last_seen_at = seen_at
    return interface


def save_event(
    db: Session,
    parsed: ParsedSyslog,
    source_ip: str,
    received_at: datetime | None = None,
) -> SyslogEvent:
    """Normalize a parsed message and persist it with device/interface upserts."""
    norm = normalize(parsed, source_ip, received_at)
    device = _upsert_device(db, norm, norm.received_at)
    # Commit the device before the interface step so that a concurrent
    # interface-conflict rollback can never discard the device row.
    db.commit()
    if norm.interface_name:
        _upsert_interface(db, device, norm.interface_name, norm.received_at)
        db.commit()

    event = SyslogEvent(
        received_at=norm.received_at,
        timestamp=norm.timestamp,
        source_ip=norm.source_ip,
        device_id=device.id,
        rfc=norm.rfc,
        facility=norm.facility,
        severity=norm.severity,
        severity_label=norm.severity_label,
        hostname=norm.hostname,
        app_name=norm.app_name,
        procid=norm.procid,
        msgid=norm.msgid,
        vendor=norm.vendor,
        interface_name=norm.interface_name,
        event_type_code=norm.event_type_code,
        event_type_id=resolver.get_id(db, norm.event_type_code),
        message=norm.message,
        raw_message=norm.raw_message,
        structured_data=norm.structured_data,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
