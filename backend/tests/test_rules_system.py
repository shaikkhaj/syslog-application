"""Detection tests: CONFIG_CHANGE and DEVICE_UNREACHABLE rules."""

from app.detection.config import DetectionConfig
from app.detection.types import AlertSeverity
from app.syslog.pipeline import process_message

CONFIG_CISCO = (
    b"<130>Jan 15 10:23:45 cfg-rtr: %SYS-5-CONFIG_I: Configured from "
    b"console by admin on vty0 (10.0.0.5)"
)
CONFIG_FORTIGATE = (
    b'<186>date=2026-01-15 time=10:23:45 devname="FGT-CFG-01" type="event" '
    b'subtype="global-setting" level="information" user="admin" '
    b'msg="Configuration is changed by administrator"'
)
CONFIG_LINUX = (
    b"<14>Jan 15 10:23:45 cfg-web01 hostagent: configuration file "
    b"/etc/nginx/nginx.conf changed by user deploy"
)
UNREACHABLE_CISCO = (
    b"<130>Jan 15 10:23:45 unr-rtr: %IPRT-4-UNREACHABLE: No route to host "
    b"10.5.5.5"
)
UNREACHABLE_LINUX = (
    b"<11>Jan 15 10:23:45 unr-web01 probe[888]: probe failed: connect to "
    b"10.9.9.9:443 - No route to host"
)


def test_cisco_config_change_low_alert(db_ready, alerts_table):
    process_message(CONFIG_CISCO, "10.35.0.1")

    alerts = alerts_table.by_type("CONFIG_CHANGE")
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == AlertSeverity.LOW.value
    assert alert.rule_name == "config_change"
    assert alert.context["actor"] == "admin"
    assert alert.context["vendor"] == "cisco"


def test_fortigate_config_change_extracts_user(db_ready, alerts_table):
    process_message(CONFIG_FORTIGATE, "10.35.0.2")

    alerts = alerts_table.by_type("CONFIG_CHANGE")
    assert len(alerts) == 1
    assert alerts[0].context["actor"] == "admin"
    assert alerts[0].context["vendor"] == "fortinet"


def test_linux_config_change_extracts_user(db_ready, alerts_table):
    process_message(CONFIG_LINUX, "10.35.0.3")

    alerts = alerts_table.by_type("CONFIG_CHANGE")
    assert len(alerts) == 1
    assert alerts[0].context["actor"] == "deploy"
    assert alerts[0].severity == AlertSeverity.LOW.value


def test_repeated_config_changes_coalesce(db_ready, alerts_table):
    ip = "10.35.0.4"
    process_message(CONFIG_CISCO, ip)
    process_message(CONFIG_CISCO, ip)

    alerts = alerts_table.by_type("CONFIG_CHANGE")
    assert len(alerts) == 1
    assert alerts[0].event_count == 2


def test_cisco_unreachable_critical_alert(db_ready, alerts_table):
    process_message(UNREACHABLE_CISCO, "10.35.0.5")

    alerts = alerts_table.by_type("DEVICE_UNREACHABLE")
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == AlertSeverity.CRITICAL.value
    assert alert.context["target"] == "10.5.5.5"
    assert alert.rule_name == "device_unreachable"


def test_linux_unreachable_critical_alert(db_ready, alerts_table):
    process_message(UNREACHABLE_LINUX, "10.35.0.6")

    alerts = alerts_table.by_type("DEVICE_UNREACHABLE")
    assert len(alerts) == 1
    assert alerts[0].severity == AlertSeverity.CRITICAL.value
    assert alerts[0].context["target"] == "10.9.9.9"


def test_unreachable_same_target_coalesces(db_ready, alerts_table):
    ip = "10.35.0.7"
    process_message(UNREACHABLE_CISCO, ip)
    process_message(UNREACHABLE_CISCO, ip)

    alerts = alerts_table.by_type("DEVICE_UNREACHABLE")
    assert len(alerts) == 1
    assert alerts[0].event_count == 2
