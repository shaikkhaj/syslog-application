"""Unit tests for vendor detection, interface extraction and normalization."""

from app.syslog.normalize import (
    detect_vendor,
    extract_interface,
    normalize,
)
from app.syslog.parser import parse_syslog

CISCO = (
    b"<134>Jan 15 10:23:45 rtr-core-01: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/1, changed state to down"
)
FORTIGATE = (
    b'<185>date=2026-01-15 time=10:23:45 devname="FGT60F-001" '
    b'devid="FG60F000000001" logid="0000000013" type="traffic" '
    b'action="deny" interface="port1" msg="denied by forward policy"'
)
JUNIPER = (
    b"<14>Jan 15 10:23:46 mx-edge-01 rpd[1234]: BGP - 10.10.10.1 External "
    b"AS 65001 keepalive error: Connection closed by remote host"
)
LINUX = (
    b"<85>1 2026-01-15T10:23:47.003Z web01 sshd - - - "
    b"Failed password for invalid user admin from 203.0.113.10 port 54321 ssh2"
)


class TestVendorDetection:
    def test_cisco(self):
        assert detect_vendor(parse_syslog(CISCO)) == "cisco"

    def test_fortinet(self):
        assert detect_vendor(parse_syslog(FORTIGATE)) == "fortinet"

    def test_juniper(self):
        assert detect_vendor(parse_syslog(JUNIPER)) == "juniper"

    def test_linux(self):
        assert detect_vendor(parse_syslog(LINUX)) == "linux"

    def test_unknown(self):
        message = parse_syslog(b"<14>Jan 15 10:23:45 h1: something odd happened")
        assert detect_vendor(message) == "unknown"


class TestInterfaceExtraction:
    def test_cisco_interface(self):
        parsed = parse_syslog(CISCO)
        assert extract_interface(parsed.message) == "GigabitEthernet0/1"

    def test_fortigate_interface(self):
        parsed = parse_syslog(FORTIGATE)
        assert extract_interface(parsed.message) == "port1"

    def test_juniper_interface(self):
        assert extract_interface("kernel: ge-0/0/0: link transition detected") == "ge-0/0/0"

    def test_no_interface(self):
        parsed = parse_syslog(LINUX)
        assert extract_interface(parsed.message) is None


class TestNormalize:
    def test_common_event_format(self):
        norm = normalize(parse_syslog(CISCO), "10.0.0.1")

        assert norm.rfc == "3164"
        assert norm.vendor == "cisco"
        assert norm.source_ip == "10.0.0.1"
        assert norm.hostname == "rtr-core-01"
        assert norm.severity == 6
        assert norm.severity_label == "info"
        assert norm.facility == 16
        assert norm.facility_name == "local0"
        assert norm.interface_name == "GigabitEthernet0/1"
        assert norm.event_type_code == "link_down"
        assert norm.received_at is not None

    def test_fortigate_hostname_fallback_from_devname(self):
        norm = normalize(parse_syslog(FORTIGATE), "10.0.0.2")

        assert norm.vendor == "fortinet"
        assert norm.hostname == "FGT60F-001"  # extracted from devname=
        assert norm.rfc == "raw"
        assert norm.severity == 1
        assert norm.severity_label == "alert"
        assert norm.interface_name == "port1"
        assert norm.event_type_code == "other"  # deny message: no rule matches yet

    def test_auth_failure_classification(self):
        norm = normalize(parse_syslog(LINUX), "10.0.0.3")
        assert norm.vendor == "linux"
        assert norm.event_type_code == "auth_failure"

    def test_bgp_down_classification(self):
        norm = normalize(parse_syslog(JUNIPER), "10.0.0.4")
        assert norm.vendor == "juniper"
        assert norm.event_type_code == "bgp_down"

    def test_unmatched_is_other(self):
        parsed = parse_syslog(b"<14>Jan 15 10:23:45 h1: something odd happened")
        norm = normalize(parsed, "10.0.0.5")
        assert norm.event_type_code == "other"
