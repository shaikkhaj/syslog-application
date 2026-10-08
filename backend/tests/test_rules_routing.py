"""Detection tests: BGP/OSPF state transitions and route changes."""

from app.detection.config import DetectionConfig
from app.detection.types import AlertSeverity, EventType
from app.db.session import SessionLocal
from app.syslog.pipeline import process_message

CISCO_BGP_DOWN = (
    b"<135>Jan 15 10:23:45 bgp-rtr: %BGP-5-ADJCHANGE: neighbor 10.10.10.1 "
    b"Down - Connection closed by remote host"
)
CISCO_BGP_UP = (
    b"<134>Jan 15 10:24:00 bgp-rtr: %BGP-5-ADJCHANGE: neighbor 10.10.10.1 "
    b"Up - Opened"
)
JUNIPER_BGP_DOWN = (
    b"<14>Jan 15 10:23:46 mx-edge rpd[1234]: BGP - 10.10.20.1 External AS "
    b"65002 keepalive error: Connection closed by remote host"
)
CISCO_OSPF_DOWN = (
    b"<134>Jan 15 10:23:47 ospf-rtr: %OSPF-5-ADJCHG: Nbr 10.10.10.2 on "
    b"GigabitEthernet0/0 from FULL to DOWN, Neighbor Down"
)
CISCO_OSPF_UP = (
    b"<134>Jan 15 10:24:10 ospf-rtr: %OSPF-5-ADJCHG: Nbr 10.10.10.2 on "
    b"GigabitEthernet0/0 from DOWN to FULL"
)
JUNIPER_OSPF_UP = (
    b"<14>Jan 15 10:24:11 mx-edge rpd[1234]: OSPF neighbor 10.10.20.2 "
    b"(via ge-0/0/0) state moved from Down to Full"
)
ROUTE_CISCO = (
    b"<134>Jan 15 10:23:49 rt-rtr: %IPRT-5-ROUTE_CHANGE: route 10.9.0.0/16 "
    b"changed via 10.10.10.2"
)
ROUTE_LINUX = (
    b"<14>Jan 15 10:23:50 rt-web01 networkd[500]: eth0: route added: "
    b"10.10.30.0/24 via 192.168.1.1"
)


def test_bgp_down_raises_high_alert_with_neighbor(db_ready, alerts_table):
    process_message(CISCO_BGP_DOWN, "10.32.0.1")

    alerts = alerts_table.by_type("BGP_DOWN")
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == AlertSeverity.HIGH.value
    assert alert.rule_name == "bgp_state"
    assert alert.context["neighbor"] == "10.10.10.1"
    assert alert.context["new_state"] == "down"
    assert alert.context["previous_state"] is None  # first observation
    assert "10.10.10.1" in alert.title


def test_bgp_up_then_down_tracks_state_transition(db_ready, alerts_table):
    ip = "10.32.0.2"
    process_message(CISCO_BGP_UP, ip)
    process_message(CISCO_BGP_DOWN, ip)

    up = alerts_table.by_type("BGP_UP")
    down = alerts_table.by_type("BGP_DOWN")
    assert len(up) == 1 and up[0].severity == AlertSeverity.INFO.value
    assert len(down) == 1
    assert down[0].context["previous_state"] == "up"
    assert down[0].context["new_state"] == "down"


def test_bgp_down_after_up_on_fresh_ip_has_no_previous_state(
    db_ready, alerts_table
):
    process_message(CISCO_BGP_DOWN, "10.32.0.3")
    alerts = alerts_table.by_type("BGP_DOWN")
    assert alerts[0].context["previous_state"] is None


def test_juniper_bgp_neighbor_extraction(db_ready, alerts_table):
    process_message(JUNIPER_BGP_DOWN, "10.32.0.4")

    alerts = alerts_table.by_type("BGP_DOWN")
    assert len(alerts) == 1
    assert alerts[0].context["neighbor"] == "10.10.20.1"
    assert alerts[0].context["vendor"] == "juniper"


def test_ospf_down_alert_and_transition_tracking(db_ready, alerts_table):
    ip = "10.32.0.5"
    process_message(CISCO_OSPF_DOWN, ip)
    process_message(CISCO_OSPF_UP, ip)

    down = alerts_table.by_type("OSPF_NEIGHBOR_DOWN")
    up = alerts_table.by_type("OSPF_NEIGHBOR_UP")
    assert len(down) == 1
    assert down[0].severity == AlertSeverity.HIGH.value
    assert down[0].context["neighbor"] == "10.10.10.2"
    assert len(up) == 1
    assert up[0].severity == AlertSeverity.INFO.value
    # The UP event now knows the neighbor was previously down.
    assert up[0].context["previous_state"] == "down"
    assert up[0].context["new_state"] == "up"


def test_juniper_ospf_up_classification_and_extraction(db_ready, alerts_table):
    process_message(JUNIPER_OSPF_UP, "10.32.0.6")

    up = alerts_table.by_type("OSPF_NEIGHBOR_UP")
    assert len(up) == 1
    assert up[0].context["neighbor"] == "10.10.20.2"
    assert up[0].context["vendor"] == "juniper"


def test_cisco_route_change_low_alert(db_ready, alerts_table):
    process_message(ROUTE_CISCO, "10.32.0.7")

    alerts = alerts_table.by_type("ROUTE_CHANGE")
    assert len(alerts) == 1
    assert alerts[0].severity == AlertSeverity.LOW.value
    assert alerts[0].context["route"] == "10.9.0.0/16"
    assert alerts[0].rule_name == "route_change"


def test_linux_route_added_detected(db_ready, alerts_table):
    process_message(ROUTE_LINUX, "10.32.0.8")

    alerts = alerts_table.by_type("ROUTE_CHANGE")
    assert len(alerts) == 1
    assert alerts[0].context["route"] == "10.10.30.0/24"


def test_same_route_coalesces_while_open(db_ready, alerts_table):
    ip = "10.32.0.9"
    process_message(ROUTE_CISCO, ip)
    process_message(ROUTE_CISCO, ip)

    alerts = alerts_table.by_type("ROUTE_CHANGE")
    assert len(alerts) == 1
    assert alerts[0].event_count == 2
