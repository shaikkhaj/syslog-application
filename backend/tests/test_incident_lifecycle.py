"""Incident lifecycle: state machine, history audit and timeline."""

from sqlalchemy import select

from app.correlation.engine import CorrelationEngine, get_correlation_engine
from app.correlation.types import IncidentStatus
from app.db.session import SessionLocal
from app.models.models import Incident, IncidentStateHistory
from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 lc-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/4, changed state to down"
)
CISCO_UP = (
    b"<134>Jan 15 10:25:00 lc-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/4, changed state to up"
)


def _one_incident(db):
    return db.execute(select(Incident)).scalars().first()


def test_state_machine_happy_path(db_ready):
    process_message(CISCO_DOWN, "10.42.0.1")
    engine = get_correlation_engine()

    with SessionLocal() as db:
        incident = _one_incident(db)
        assert incident.status == "OPEN"

        engine.transition_status(incident, IncidentStatus.ACKNOWLEDGED, db, "alice")
        assert incident.status == "ACKNOWLEDGED"
        assert incident.acknowledged_by == "alice"
        assert incident.acknowledged_at is not None

        engine.transition_status(incident, IncidentStatus.RESOLVED, db, "alice")
        assert incident.status == "RESOLVED"
        assert incident.resolved_at is not None

        engine.transition_status(incident, IncidentStatus.CLOSED, db, "alice")
        assert incident.status == "CLOSED"
        assert incident.closed_at is not None

        history = list(
            db.execute(
                select(IncidentStateHistory)
                .where(IncidentStateHistory.incident_id == incident.id)
                .order_by(IncidentStateHistory.changed_at.asc())
            ).scalars()
        )
        transitions = [(row.from_status, row.to_status) for row in history]
        assert transitions == [
            (None, "OPEN"),
            ("OPEN", "ACKNOWLEDGED"),
            ("ACKNOWLEDGED", "RESOLVED"),
            ("RESOLVED", "CLOSED"),
        ]
        assert history[1].changed_by == "alice"


def test_invalid_transitions_rejected(db_ready):
    process_message(CISCO_DOWN, "10.42.0.2")
    engine = get_correlation_engine()

    with SessionLocal() as db:
        incident = _one_incident(db)
        # OPEN cannot go straight to CLOSED
        try:
            engine.transition_status(incident, IncidentStatus.CLOSED, db)
            raise AssertionError("expected ValueError")
        except ValueError:
            db.rollback()

        engine.transition_status(incident, IncidentStatus.ACKNOWLEDGED, db)
        # ACKNOWLEDGED cannot go back to INVESTIGATING
        try:
            engine.transition_status(incident, IncidentStatus.INVESTIGATING, db)
            raise AssertionError("expected ValueError")
        except ValueError:
            db.rollback()

        engine.transition_status(incident, IncidentStatus.RESOLVED, db)
        # RESOLVED cannot be acknowledged again
        try:
            engine.transition_status(incident, IncidentStatus.ACKNOWLEDGED, db)
            raise AssertionError("expected ValueError")
        except ValueError:
            db.rollback()

        db.refresh(incident)
        assert incident.status == "RESOLVED"


def test_timeline_contains_creation_alert_event_and_transitions(db_ready):
    ip = "10.42.0.3"
    process_message(CISCO_DOWN, ip)
    process_message(CISCO_UP, ip)
    engine = get_correlation_engine()

    with SessionLocal() as db:
        incident = _one_incident(db)
        engine.transition_status(incident, IncidentStatus.ACKNOWLEDGED, db, "bob")
        engine.transition_status(incident, IncidentStatus.RESOLVED, db, "bob")

        entries = engine.build_timeline(incident, db)
        types = {entry["type"] for entry in entries}
        assert {"state_change", "alert", "event"} <= types

        # chronological order
        timestamps = [entry["timestamp"] for entry in entries]
        assert timestamps == sorted(timestamps)

        # creation + ack + resolve recorded
        state_changes = [e for e in entries if e["type"] == "state_change"]
        assert state_changes[0]["from_status"] is None  # incident creation
        assert [e["to_status"] for e in state_changes] == [
            "OPEN",
            "ACKNOWLEDGED",
            "RESOLVED",
        ]

        # recovery alert flagged on the timeline
        alert_entries = [e for e in entries if e["type"] == "alert"]
        assert any(entry.get("recovery") for entry in alert_entries)

        # underlying syslog events present
        event_entries = [e for e in entries if e["type"] == "event"]
        assert any("GigabitEthernet0/4" in (entry.get("message") or "") for entry in event_entries)


def test_correlation_key_and_score_persisted(db_ready):
    process_message(CISCO_DOWN, "10.42.0.4")

    with SessionLocal() as db:
        incident = _one_incident(db)
        assert incident.correlation_key.startswith("device:")
        assert ":interface:" in incident.correlation_key
        assert incident.score > 0
        assert incident.root_cause is not None
        assert incident.root_cause_candidates and isinstance(
            incident.root_cause_candidates, list
        )
