"""Unit tests for RFC3164 / RFC5424 / raw syslog parsing."""

from datetime import datetime, timezone

import pytest

from app.syslog.parser import parse_syslog

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestRfc3164:
    def test_cisco_style_message(self):
        raw = (
            b"<134>Jan 15 10:23:45 rtr-core-01: %LINK-3-UPDOWN: Interface "
            b"GigabitEthernet0/1, changed state to down"
        )
        parsed = parse_syslog(raw, now=NOW)

        assert parsed.rfc == "3164"
        assert parsed.pri == 134
        assert parsed.facility == 16  # local0
        assert parsed.severity == 6  # info
        assert parsed.hostname == "rtr-core-01"
        assert parsed.message.startswith("%LINK-3-UPDOWN")
        assert parsed.timestamp is not None
        assert parsed.timestamp.year == 2026
        assert parsed.timestamp.month == 1
        assert parsed.timestamp.day == 15

    def test_bsd_style_with_process(self):
        raw = b"<34>Oct 11 22:14:15 mymachine su[1234]: 'su root' failed for lonvick"
        parsed = parse_syslog(raw, now=NOW)

        assert parsed.rfc == "3164"
        assert parsed.hostname == "mymachine"
        assert parsed.message == "su[1234]: 'su root' failed for lonvick"
        assert parsed.facility == 4  # auth
        assert parsed.severity == 2  # critical

    def test_cisco_message_without_hostname(self):
        raw = b"<130>Jan 15 10:23:45.123: %SYS-5-CONFIG_I: Configured from console"
        parsed = parse_syslog(raw, now=NOW)

        assert parsed.rfc == "3164"
        assert parsed.hostname is None
        assert parsed.message.startswith("%SYS-5-CONFIG_I")

    def test_year_inferred_across_new_year(self):
        raw = b"<14>Dec 31 23:59:59 host1 kernel: year rollover test"
        parsed = parse_syslog(raw, now=datetime(2026, 1, 2, tzinfo=timezone.utc))

        assert parsed.timestamp is not None
        assert parsed.timestamp.year == 2025

    def test_fractional_seconds(self):
        raw = b"<134>Jan 15 10:23:45.123456 rtr1: message"
        parsed = parse_syslog(raw, now=NOW)

        assert parsed.timestamp.microsecond == 123456


class TestRfc5424:
    def test_full_message_with_structured_data(self):
        raw = (
            b'<165>1 2026-01-15T10:23:45.000Z web01 sshd 1234 ID47 '
            b'[origin ip="10.0.0.5"][meta sequenceId="1"] '
            b"Failed password for root from 1.2.3.4 port 22 ssh2"
        )
        parsed = parse_syslog(raw, now=NOW)

        assert parsed.rfc == "5424"
        assert parsed.pri == 165
        assert parsed.facility == 20  # local4
        assert parsed.severity == 5  # notice
        assert parsed.timestamp == datetime(2026, 1, 15, 10, 23, 45, tzinfo=timezone.utc)
        assert parsed.hostname == "web01"
        assert parsed.app_name == "sshd"
        assert parsed.procid == "1234"
        assert parsed.msgid == "ID47"
        assert parsed.structured_data == {
            "origin": {"ip": "10.0.0.5"},
            "meta": {"sequenceId": "1"},
        }
        assert parsed.message.endswith("ssh2")

    def test_nil_fields(self):
        raw = b"<134>1 - rtr1 Cisco-IOSd - - - %LINK-3-UPDOWN: changed state to up"
        parsed = parse_syslog(raw, now=NOW)

        assert parsed.rfc == "5424"
        assert parsed.timestamp is None
        assert parsed.app_name == "Cisco-IOSd"
        assert parsed.procid is None
        assert parsed.msgid is None
        assert parsed.structured_data == {}
        assert parsed.message == "%LINK-3-UPDOWN: changed state to up"

    def test_message_with_escaped_quotes_in_sd(self):
        raw = (
            b'<134>1 2026-01-15T10:00:00Z fgt - - - '
            b'[fgt logid="0100020001" note="said \\"hello\\""] login attempt'
        )
        parsed = parse_syslog(raw, now=NOW)

        assert parsed.structured_data["fgt"]["note"] == 'said "hello"'
        assert parsed.message == "login attempt"

    def test_unterminated_structured_data_falls_back(self):
        raw = b"<134>1 2026-01-15T10:00:00Z host app - - [broken no-close message"
        parsed = parse_syslog(raw, now=NOW)

        # Falls back through 3164 to raw rather than dropping the message.
        assert parsed.rfc == "raw"
        assert "broken" in parsed.message


class TestRawFallbackAndEdgeCases:
    def test_fortigate_kv_format(self):
        raw = (
            b'<185>date=2026-01-15 time=10:23:45 devname="FGT60F-001" '
            b'devid="FG60F000000001" type="traffic" action="deny" '
            b'msg="denied by forward policy"'
        )
        parsed = parse_syslog(raw, now=NOW)

        assert parsed.rfc == "raw"
        assert parsed.pri == 185
        assert parsed.facility == 23  # local7
        assert parsed.severity == 1  # alert
        assert "devname=" in parsed.message

    def test_message_without_pri(self):
        parsed = parse_syslog(b"plain message without pri", now=NOW)

        assert parsed.rfc == "raw"
        assert parsed.pri is None
        assert parsed.severity is None
        assert parsed.message == "plain message without pri"

    def test_invalid_pri_value_is_ignored(self):
        parsed = parse_syslog(b"<999>Jan 15 10:23:45 host: msg", now=NOW)

        assert parsed.pri is None
        # Still parsed as RFC3164 because the payload itself is valid.
        assert parsed.rfc == "3164"
        assert parsed.hostname == "host"

    def test_empty_message_raises(self):
        with pytest.raises(ValueError):
            parse_syslog(b"")

        with pytest.raises(ValueError):
            parse_syslog(b"   \n")

    def test_non_utf8_bytes_do_not_crash(self):
        parsed = parse_syslog(b"<134>Jan 15 10:23:45 host: caf\xe9 message", now=NOW)

        assert parsed.rfc == "3164"
        assert "message" in parsed.message
