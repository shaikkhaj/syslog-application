"""Integration tests: incident dedupe, time window, custom window config."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.correlation.config import CorrelationConfig
from app.correlation.engine import CorrelationEngine
from app.db.session import SessionLocal
from app.models.models import Alert, Incident
from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 w-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/3, changed state to down"
)
CISCO_UP = (
    b"<134>Jan 15 10:24:00 w-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/3, changed state to up"
)
CISCO_BGP_DOWN = (
    b"<135>Jan 15 10:23:45 w-rtr: %BGP-5-ADJCHANGE: neighbor 10.10.10.1 "
    b"Down - Connection closed by remote host"
)


def _incidents(db):
    return list(db.execute(select(Incident)).scalars().all())


def test_repeated_failure_does_not_duplicate_incidents(db_ready):
    ip = "10.41.0.1"
    for _ in range(3):
        process_message(CISCO_DOWN, ip)

    with SessionLocal() as db:
        incidents = _incidents(db)
        assert len(incidents) == 1
        assert incidents[0].alert_count == 1  # alerts coalesced too


def test_alert_outside_window_creates_new_incident(db_ready):
    ip = "10.41.0.2"
    process_message(CISCO_DOWN, ip)

    stale = datetime.now(timezone.utc) - timedelta(seconds=3600)
    with SessionLocal() as db:
        db.execute(update(Incident).values(last_seen_at=stale, first_seen_at=stale))
        db.commit()

    # BGP down would causally match the (now stale) interface incident if the
    # window were ignored — with the default 300s window it starts a new one.
    process_message(CISCO_BGP_DOWN, ip)

    with SessionLocal() as db:
        incidents = list(db.execute(select(Incident)).scalars().all())
        assert len(incidents) == 2
        keys = {incident.correlation_key for incident in incidents}
        assert len(keys) == 2


def test_unrelated_alerts_stay_separate_incidents(db_ready):
    process_message(CISCO_DOWN, "10.41.0.3")
    process_message(
        b"<133>Jan 15 10:23:45 w-sw: %CPU_FALLBACK-3-HIGH_CPU: "
        b"cpu_utilization=95% threshold=80% interval=60s",
        "10.41.0.4",
    )

    with SessionLocal() as db:
        assert len(_incidents(db)) == 2


def test_alert_joined_to_incident_and_event(db_ready):
    ip = "10.41.0.5"
    process_message(CISCO_DOWN, ip)

    with SessionLocal() as db:
        incident = _incidents(db)[0]
        alerts = list(
            db.execute(select(Alert).where(Alert.incident_id == incident.id)).scalars()
        )
        assert len(alerts) == 1
        assert alerts[0].incident_id == incident.id
        assert alerts[0].event_id is not None  # triggering event linked


def test_resolved_incident_not_reused_for_new_failure(db_ready):
    ip = "10.41.0.6"
    process_message(CISCO_DOWN, ip)

    with SessionLocal() as db:
        incident = _incidents(db)[0]
        incident.status = "RESOLVED"
        incident.resolved_at = datetime.now(timezone.utc)
        db.commit()

    process_message(CISCO_DOWN, ip)  # same failure resumes after resolution

    with SessionLocal() as db:
        incidents = _incidents(db)
        assert len(incidents) == 2  # fresh incident after resolution


def test_correlation_disabled_engine_creates_nothing(db_ready):
    ip = "10.41.0.7"
    process_message(CISCO_DOWN, ip)
    with SessionLocal() as db:
        before = len(_incidents(db))

    engine = CorrelationEngine(config=CorrelationConfig(enabled=False))
    with SessionLocal() as db:
        alert = db.execute(
            select(Alert).order_by(Alert.id.desc()).limit(1)
        ).scalar_one()
        assert engine.process_alerts([alert], db) == []
