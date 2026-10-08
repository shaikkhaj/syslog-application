"""Detection tests: AUTH_FAILURE threshold/window rule."""

from datetime import datetime, timedelta, timezone

from app.detection.config import DetectionConfig
from app.detection.rules.auth_rules import AuthFailureRule
from app.detection.types import AlertSeverity
from app.db.session import SessionLocal
from app.syslog.pipeline import process_message

SSHD_FAILURE = (
    b"<85>1 2026-01-15T10:23:47.003Z auth-web01 sshd - - - Failed password "
    b"for root from 203.0.113.77 port 2222 ssh2"
)
CISCO_LOGIN_FAILURE = (
    b"<131>Jan 15 10:23:45 auth-sw: %SEC_LOGIN-5-LOGIN_FAILED: Login failed "
    b"[user: root] [Source: 203.0.113.88] at 10:23:45 UTC"
)


def test_single_failure_does_not_alert(db_ready, alerts_table):
    process_message(SSHD_FAILURE, "10.33.0.1")
    assert alerts_table.by_type("AUTH_FAILURE") == []


def test_threshold_crossing_raises_medium_alert(db_ready, alerts_table):
    ip = "10.33.0.2"
    for _ in range(5):  # default threshold = 5
        process_message(SSHD_FAILURE, ip)

    alerts = alerts_table.by_type("AUTH_FAILURE")
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == AlertSeverity.MEDIUM.value
    assert alert.rule_name == "auth_failure_threshold"
    assert alert.context["source_ip"] == "203.0.113.77"
    assert alert.context["failures_in_window"] == 5
    assert alert.context["threshold"] == 5
    assert alert.device_id is not None


def test_escalation_to_high_at_three_times_threshold(db_ready, alerts_table):
    ip = "10.33.0.3"
    for _ in range(15):  # 3 × threshold = 15
        process_message(SSHD_FAILURE, ip)

    alerts = alerts_table.by_type("AUTH_FAILURE")
    assert len(alerts) == 1  # still a single coalesced alert
    assert alerts[0].severity == AlertSeverity.HIGH.value
    assert alerts[0].event_count == 11  # created at #5, updated 6..15


def test_failures_from_different_sources_tracked_separately(
    db_ready, alerts_table
):
    ip = "10.33.0.4"
    for _ in range(5):
        process_message(SSHD_FAILURE, ip)
    process_message(
        b"<85>1 2026-01-15T10:24:00.000Z auth-web01 sshd - - - Failed password "
        b"for admin from 198.51.100.9 port 3333 ssh2",
        ip,
    )

    alerts = alerts_table.by_type("AUTH_FAILURE")
    assert len(alerts) == 1  # only the first source crossed the threshold
    assert alerts[0].context["source_ip"] == "203.0.113.77"


def test_failures_outside_window_are_ignored(db_ready, event_factory):
    ip = "10.33.0.5"
    old = datetime.now(timezone.utc) - timedelta(seconds=3600)
    for _ in range(4):
        event_factory(
            ip,
            "Failed password for root from 203.0.113.77 port 2222 ssh2",
            event_type="AUTH_FAILURE",
            vendor="linux",
            received_at=old,
        )
    current = event_factory(
        ip,
        "Failed password for root from 203.0.113.77 port 2222 ssh2",
        event_type="AUTH_FAILURE",
        vendor="linux",
    )

    with SessionLocal() as db:
        results = list(AuthFailureRule().evaluate(current, db, DetectionConfig()))
    assert results == []  # 1 fresh failure < threshold 5; the4 old ones expired


def test_configurable_auth_window_and_threshold(db_ready, event_factory):
    ip = "10.33.0.6"
    now = datetime.now(timezone.utc)
    for index in range(2):
        event_factory(
            ip,
            "Failed password for root from 203.0.113.77 port 2222 ssh2",
            event_type="AUTH_FAILURE",
            vendor="linux",
            received_at=now - timedelta(seconds=30 * index),
        )
    current = event_factory(
        ip,
        "Failed password for root from 203.0.113.77 port 2222 ssh2",
        event_type="AUTH_FAILURE",
        vendor="linux",
        received_at=now,
    )

    custom = DetectionConfig(auth_failure_threshold=5, auth_failure_window_seconds=120)
    with SessionLocal() as db:
        assert list(AuthFailureRule().evaluate(current, db, custom)) == []

    custom_below = DetectionConfig(
        auth_failure_threshold=3, auth_failure_window_seconds=600
    )
    with SessionLocal() as db:
        results = list(AuthFailureRule().evaluate(current, db, custom_below))
    assert len(results) == 1
    assert results[0].context["failures_in_window"] == 3


def test_cisco_login_failures_detected(db_ready, alerts_table):
    ip = "10.33.0.7"
    for _ in range(5):
        process_message(CISCO_LOGIN_FAILURE, ip)

    alerts = alerts_table.by_type("AUTH_FAILURE")
    assert len(alerts) == 1
    assert alerts[0].context["vendor"] == "cisco"
