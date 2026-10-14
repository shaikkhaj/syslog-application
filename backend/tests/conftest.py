"""Shared test fixtures.

Environment variables are set BEFORE any application import so that the
settings/engine used by the app point at a throwaway SQLite database and
the network listeners stay disabled during tests.
"""

import os
import pathlib
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="syslog_platform_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR.replace(chr(92), '/')}/test.db"
os.environ["SYSLOG_LISTENERS_ENABLED"] = "false"
# Intentionally unreachable so the health check exercises the error path.
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_alerts():
    """Start every test with clean alerts/incidents tables.

    The SQLite test database is shared across the whole session, while alert
    and incident assertions are usually exact ("exactly one incident").
    """
    yield
    try:
        from sqlalchemy import delete

        from app.db.session import SessionLocal
        from app.models.models import (
            Alert,
            Incident,
            IncidentAlert,
            IncidentEvent,
            IncidentStateHistory,
        )

        with SessionLocal() as session:
            session.execute(delete(IncidentStateHistory))
            session.execute(delete(IncidentEvent))
            session.execute(delete(IncidentAlert))
            session.execute(delete(Alert))
            session.execute(delete(Incident))
            from app.models.models import TopologyLink

            session.execute(delete(TopologyLink))
            session.commit()
    except Exception:  # pragma: no cover - tables may not exist yet
        pass


@pytest.fixture()
def alerts_table(db_ready):
    """Return a helper to query alerts within a test."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.models import Alert

    class Alerts:
        @staticmethod
        def all():
            with SessionLocal() as session:
                return list(session.execute(select(Alert)).scalars())

        @staticmethod
        def by_type(code: str):
            with SessionLocal() as session:
                return list(
                    session.execute(
                        select(Alert).where(Alert.event_type == code)
                    ).scalars()
                )

    return Alerts


@pytest.fixture()
def event_factory(db_ready):
    """Insert normalized events directly (supports backdating for windows)."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.models import Device, SyslogEvent

    def _create(
        ip: str,
        message: str,
        *,
        event_type: str = "OTHER",
        hostname: str | None = None,
        vendor: str = "linux",
        interface: str | None = None,
        received_at: datetime | None = None,
        severity: int = 6,
    ):
        with SessionLocal() as session:
            device = session.execute(
                select(Device).where(Device.ip_address == ip)
            ).scalar_one_or_none()
            if device is None:
                device = Device(
                    ip_address=ip, hostname=hostname or ip, vendor=vendor
                )
                session.add(device)
                session.flush()
            event = SyslogEvent(
                received_at=received_at or datetime.now(timezone.utc),
                timestamp=None,
                source_ip=ip,
                device_id=device.id,
                rfc="3164",
                facility=16,
                severity=severity,
                severity_label="info",
                hostname=hostname,
                vendor=vendor,
                interface_name=interface,
                event_type_code=event_type,
                message=message,
                raw_message=message,
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            session.expunge(event)
            return event

    return _create


@pytest.fixture(scope="session")
def client():
    """Boot the full application (DB init + pipeline) and yield a test client."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_ready():
    """Ensure tables exist and the event type catalog is seeded (idempotent)."""
    from app.db.init_db import init_db
    from app.syslog.event_types import resolver

    init_db()
    resolver.invalidate()
    return True


@pytest.fixture()
def db_session(db_ready):
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session
