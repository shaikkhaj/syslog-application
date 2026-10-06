"""Integration tests: parse → normalize → store (SQLite-backed)."""

from sqlalchemy import func, select

from app.models.models import Device, EventType, Interface, SyslogEvent
from app.syslog.event_types import resolver
from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 rtr-core-01: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/1, changed state to down"
)
CISCO_UP = (
    b"<134>Jan 15 10:24:00 rtr-core-01: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/1, changed state to up"
)
FORTIGATE = (
    b'<185>date=2026-01-15 time=10:23:45 devname="FGT60F-001" '
    b'devid="FG60F000000001" type="traffic" action="deny" '
    b'interface="port1" msg="denied by forward policy"'
)


def test_ingest_creates_event_device_and_interface(db_ready, db_session):
    event = process_message(CISCO_DOWN, "10.20.0.11")
    db_session.expire_all()

    device = db_session.get(Device, event.device_id)
    assert device is not None
    assert device.ip_address == "10.20.0.11"
    assert device.hostname == "rtr-core-01"
    assert device.vendor == "cisco"

    assert event.rfc == "3164"
    assert event.vendor == "cisco"
    assert event.severity == 6
    assert event.severity_label == "info"
    assert event.facility == 16
    assert event.interface_name == "GigabitEthernet0/1"
    assert event.event_type_code == "link_down"
    assert event.event_type_id is not None
    assert event.timestamp is not None
    assert "changed state to down" in event.message

    interface = db_session.execute(
        select(Interface).where(
            Interface.device_id == device.id,
            Interface.name == "GigabitEthernet0/1",
        )
    ).scalar_one_or_none()
    assert interface is not None


def test_same_source_ip_reuses_device(db_ready, db_session):
    first = process_message(CISCO_DOWN, "10.20.0.12")
    second = process_message(CISCO_UP, "10.20.0.12")
    db_session.expire_all()

    assert first.device_id == second.device_id
    count = db_session.execute(
        select(func.count()).select_from(Device).where(Device.ip_address == "10.20.0.12")
    ).scalar_one()
    assert count == 1


def test_fortigate_event_normalization(db_ready, db_session):
    event = process_message(FORTIGATE, "10.20.0.21")

    assert event.vendor == "fortinet"
    assert event.hostname == "FGT60F-001"
    assert event.rfc == "raw"
    assert event.severity == 1
    assert event.severity_label == "alert"
    assert event.interface_name == "port1"
    assert event.raw_message.startswith("<185>date=")


def test_event_type_catalog_seeded(db_ready, db_session):
    process_message(CISCO_DOWN, "10.20.0.31")

    codes = {
        row.code
        for row in db_session.execute(select(EventType)).scalars()
    }
    assert {"link_down", "link_up", "bgp_down", "auth_failure", "other"} <= codes
    assert resolver.get_id(db_session, "link_down") is not None


def test_empty_message_raises(db_ready):
    try:
        process_message(b"   ", "10.20.0.99")
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty message")
