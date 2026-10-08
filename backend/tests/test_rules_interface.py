"""Detection tests: INTERFACE_DOWN/UP and LINK_FLAP rules."""

from datetime import datetime, timedelta, timezone

from app.detection.config import DetectionConfig
from app.detection.rules.interface_rules import InterfaceStateRule, LinkFlapRule
from app.detection.types import AlertSeverity, EventType
from app.db.session import SessionLocal
from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 iface-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/7, changed state to down"
)
CISCO_UP = (
    b"<134>Jan 15 10:24:00 iface-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/7, changed state to up"
)


def test_interface_down_raises_high_alert(db_ready, alerts_table):
    process_message(CISCO_DOWN, "10.31.0.1")

    alerts = alerts_table.by_type("INTERFACE_DOWN")
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == AlertSeverity.HIGH.value
    assert alert.status == "new"
    assert alert.rule_name == "interface_state"
    assert "GigabitEthernet0/7" in alert.title
    assert alert.context["interface"] == "GigabitEthernet0/7"
    assert alert.context["vendor"] == "cisco"
    assert alert.device_id is not None
    assert alert.event_id is not None
    assert alert.event_count == 1


def test_interface_up_raises_info_alert(db_ready, alerts_table):
    process_message(CISCO_UP, "10.31.0.2")

    alerts = alerts_table.by_type("INTERFACE_UP")
    assert len(alerts) == 1
    assert alerts[0].severity == AlertSeverity.INFO.value
    assert "GigabitEthernet0/7" in alerts[0].title


def test_repeated_down_events_coalesce_into_one_alert(db_ready, alerts_table):
    process_message(CISCO_DOWN, "10.31.0.3")
    process_message(CISCO_DOWN, "10.31.0.3")

    alerts = alerts_table.by_type("INTERFACE_DOWN")
    assert len(alerts) == 1  # one alert, not two
    assert alerts[0].event_count == 2


def test_link_flap_below_threshold_no_alert(db_ready, alerts_table):
    # Default threshold = 4 transitions; two must stay silent.
    process_message(CISCO_DOWN, "10.31.0.4")
    process_message(CISCO_UP, "10.31.0.4")

    assert alerts_table.by_type("LINK_FLAP") == []
    assert len(alerts_table.by_type("INTERFACE_DOWN")) == 1


def test_link_flap_at_threshold_creates_single_critical_alert(
    db_ready, alerts_table
):
    ip = "10.31.0.5"
    for _ in range(2):  # down, up, down, up = 4 transitions
        process_message(CISCO_DOWN, ip)
        process_message(CISCO_UP, ip)

    flaps = alerts_table.by_type("LINK_FLAP")
    assert len(flaps) == 1  # many transitions → one alert
    assert flaps[0].severity == AlertSeverity.CRITICAL.value
    assert flaps[0].context["transitions_in_window"] >= 4
    assert flaps[0].context["threshold"] == 4
    assert "flapping" in flaps[0].title


def test_link_flap_further_transitions_coalesce(db_ready, alerts_table):
    ip = "10.31.0.6"
    for _ in range(3):  # 6 transitions total
        process_message(CISCO_DOWN, ip)
        process_message(CISCO_UP, ip)

    flaps = alerts_table.by_type("LINK_FLAP")
    assert len(flaps) == 1
    assert flaps[0].event_count == 3  # created at #4, updated at #5 and #6


def test_link_flap_counts_only_events_inside_window(db_ready, event_factory):
    ip = "10.31.0.7"
    old = datetime.now(timezone.utc) - timedelta(seconds=400)  # outside 300s
    recent = datetime.now(timezone.utc)
    for index in range(3):
        event_factory(
            ip,
            f"old transition {index}",
            event_type="INTERFACE_DOWN" if index % 2 == 0 else "INTERFACE_UP",
            interface="GigabitEthernet0/9",
            received_at=old,
        )
    current = event_factory(
        ip,
        "new transition",
        event_type="INTERFACE_DOWN",
        interface="GigabitEthernet0/9",
        received_at=recent,
    )

    with SessionLocal() as db:
        results = list(
            LinkFlapRule().evaluate(current, db, DetectionConfig())
        )
    assert results == []  # only 1 transition inside the window (needs 4)


def test_link_flap_threshold_is_configurable(db_ready, event_factory):
    ip = "10.31.0.8"
    now = datetime.now(timezone.utc)
    event_factory(
        ip,
        "earlier transition",
        event_type="INTERFACE_UP",
        interface="Gi0/8",
        received_at=now - timedelta(seconds=10),
    )
    current = event_factory(
        ip,
        "current transition",
        event_type="INTERFACE_DOWN",
        interface="Gi0/8",
        received_at=now,
    )

    custom = DetectionConfig(link_flap_threshold=2, link_flap_window_seconds=60)
    with SessionLocal() as db:
        results = list(LinkFlapRule().evaluate(current, db, custom))
    assert len(results) == 1
    assert results[0].event_type == EventType.LINK_FLAP
    assert results[0].context["transitions_in_window"] == 2


def test_interface_rule_ignores_unrelated_events(db_ready, event_factory):
    event = event_factory(
        "10.31.0.9", "some other message", event_type="CONFIG_CHANGE"
    )
    # The engine gates evaluation with applies_to(); unrelated event
    # types are never handed to these rules.
    assert InterfaceStateRule().applies_to(event) is False
    assert LinkFlapRule().applies_to(event) is False
