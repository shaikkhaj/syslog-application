"""Correlation scenarios: link failure, flap, BGP/OSPF, ISP outage, examples."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.models import Incident, IncidentAlert
from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 sc-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/2, changed state to down"
)
CISCO_UP = (
    b"<134>Jan 15 10:24:00 sc-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/2, changed state to up"
)
CISCO_UNREACHABLE = (
    b"<130>Jan 15 10:23:46 sc-rtr: %IPRT-4-UNREACHABLE: No route to host 10.5.5.5"
)
CISCO_ROUTE = (
    b"<134>Jan 15 10:23:47 sc-rtr: %IPRT-5-ROUTE_CHANGE: route 10.9.0.0/16 "
    b"changed via 10.10.10.2"
)
CISCO_BGP_DOWN = (
    b"<135>Jan 15 10:23:45 sc-bgp: %BGP-5-ADJCHANGE: neighbor 10.10.10.1 "
    b"Down - Connection closed by remote host"
)
CISCO_OSPF_DOWN = (
    b"<134>Jan 15 10:23:45 sc-ospf: %OSPF-5-ADJCHG: Nbr 10.10.10.2 on "
    b"GigabitEthernet0/0 from FULL to DOWN, Neighbor Down"
)
FGT_VPN_DOWN = (
    b'<186>date=2026-01-15 time=10:23:50 devname="FGT-SC-01" type="event" '
    b'subtype="ipsec" level="error" tunnel="FGT-to-DC" msg="IPSec tunnel is down"'
)


def _incidents(db):
    return list(db.execute(select(Incident)).scalars().all())


def _alert_ids_for(db, incident):
    return [
        row.alert_id
        for row in db.execute(
            select(IncidentAlert).where(IncidentAlert.incident_id == incident.id)
        ).scalars()
    ]


def test_link_failure_correlated_into_one_incident(db_ready):
    ip = "10.40.0.1"
    process_message(CISCO_DOWN, ip)
    process_message(CISCO_UNREACHABLE, ip)
    process_message(CISCO_ROUTE, ip)

    with SessionLocal() as db:
        incidents = _incidents(db)
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.status == "OPEN"
        assert incident.severity == "CRITICAL"  # DEVICE_UNREACHABLE alert is CRITICAL
        assert incident.alert_count == 3
        assert incident.category == "interface"
        assert len(incident.affected_devices or []) == 1
        assert incident.confidence is not None and incident.confidence >= 0.9
        candidates = incident.root_cause_candidates or []
        assert candidates[0]["code"] == "interface_failure"
        assert len(_alert_ids_for(db, incident)) == 3


def test_link_flap_becomes_single_incident(db_ready):
    ip = "10.40.0.2"
    for _ in range(2):  # down, up, down, up (+ flap alert on the 4th)
        process_message(CISCO_DOWN, ip)
        process_message(CISCO_UP, ip)

    with SessionLocal() as db:
        incidents = _incidents(db)
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.severity == "CRITICAL"  # LINK_FLAP dominates
        assert incident.alert_count == 3  # down (coalesced), up (coalesced), flap
        assert "INTERFACE" in (incident.root_cause or "").upper() or "Interface" in (
            incident.root_cause or ""
        )


def test_bgp_failure_with_route_change(db_ready):
    ip = "10.40.0.3"
    process_message(CISCO_BGP_DOWN, ip)
    process_message(CISCO_ROUTE, ip)

    with SessionLocal() as db:
        incidents = _incidents(db)
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.alert_count == 2
        assert incident.severity == "HIGH"
        assert incident.category == "routing"
        assert (incident.root_cause_candidates or [])[0]["code"] == "bgp_peer_failure"


def test_ospf_failure_with_route_change(db_ready):
    ip = "10.40.0.4"
    process_message(CISCO_OSPF_DOWN, ip)
    process_message(CISCO_ROUTE, ip)

    with SessionLocal() as db:
        incidents = _incidents(db)
        assert len(incidents) == 1
        incident = incidents[0]
        assert (incident.root_cause_candidates or [])[0]["code"] == (
            "ospf_adjacency_failure"
        )


def test_isp_outage_two_devices_same_peer(db_ready):
    # Two edge routers lose the same BGP peer → one upstream incident.
    process_message(CISCO_BGP_DOWN, "10.40.0.5")
    process_message(
        b"<135>Jan 15 10:23:46 sc-bgp2: %BGP-5-ADJCHANGE: neighbor 10.10.10.1 "
        b"Down - Connection closed by remote host",
        "10.40.0.6",
    )

    with SessionLocal() as db:
        incidents = _incidents(db)
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.alert_count == 2
        assert len(incident.affected_devices or []) == 2
        top = (incident.root_cause_candidates or [])[0]
        assert top["code"] == "upstream_isp_outage"
        assert top["confidence"] >= 0.9


def test_requirement_example_multi_type_single_incident(db_ready):
    """INTERFACE_DOWN + unreachable + route + VPN in one window = 1 incident."""
    ip = "10.40.0.7"
    process_message(CISCO_DOWN, ip)
    process_message(CISCO_UNREACHABLE, ip)
    process_message(CISCO_ROUTE, ip)
    process_message(FGT_VPN_DOWN, ip)

    with SessionLocal() as db:
        incidents = _incidents(db)
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.alert_count == 4
        assert incident.severity == "CRITICAL"  # unreachable alert is CRITICAL
        top = (incident.root_cause_candidates or [])[0]
        assert top["code"] == "interface_failure"
        # corroborating evidence raised the confidence
        assert top["confidence"] >= 0.95
