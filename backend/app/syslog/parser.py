"""Syslog wire-format parsing.

Supports:
  * RFC 5424 — ``<PRI>VERSION TIMESTAMP HOSTNAME APP PROCID MSGID SD MSG``
  * RFC 3164 — ``<PRI>Mmm dd hh:mm:ss hostname: MSG`` (BSD / Cisco style)
  * raw      — ``<PRI>payload`` fallback for vendor formats such as
               FortiGate's ``date=... time=... devname=...`` header style.

The parser never performs I/O and is fully covered by unit tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

PRI_RE = re.compile(r"^<(?P<pri>\d{1,3})>")
RFC5424_VERSION_RE = re.compile(r"^(?P<version>\d{1,2})\s")
RFC3164_TIMESTAMP_RE = re.compile(
    r"^(?P<ts>[A-Z][a-z]{2}\s{1,2}\d{1,2}\s\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d{1,6}))?(?::|\s+)(?P<rest>.+)$"
)
SD_PARAM_RE = re.compile(r'(?P<key>[\w.\-]+)="(?P<value>(?:[^"\\]|\\.)*)"')

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


@dataclass
class ParsedSyslog:
    """Result of parsing a single syslog datagram/frame."""

    raw: str
    rfc: str  # "5424" | "3164" | "raw"
    pri: int | None = None
    facility: int | None = None
    severity: int | None = None
    timestamp: datetime | None = None
    hostname: str | None = None
    app_name: str | None = None
    procid: str | None = None
    msgid: str | None = None
    structured_data: dict | None = field(default=None)
    message: str = ""


def _unescape(value: str) -> str:
    return (
        value.replace(r"\\", "\x00")
        .replace(r"\"", '"')
        .replace(r"\]", "]")
        .replace("\x00", "\\")
    )


def _parse_structured_data(text: str) -> tuple[dict | None, str, bool]:
    """Parse the SD portion of an RFC5424 message.

    Returns ``(structured_data, message, ok)``. ``ok`` is False when an
    SD-ELEMENT is opened but never terminated (malformed message).
    """
    # NIL structured data: "-" alone, or "-" followed by the MSG.
    if text == "-" or text == "":
        return {}, "", True
    if text.startswith("- "):
        return {}, text[2:], True
    sd: dict[str, dict[str, str]] = {}
    i = 0
    n = len(text)
    while i < n and text[i] == "[":
        j = i + 1
        in_quote = False
        escaped = False
        while j < n:
            char = text[j]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quote = not in_quote
            elif char == "]" and not in_quote:
                break
            j += 1
        if j >= n:
            return None, "", False  # unterminated SD-ELEMENT
        element = text[i + 1 : j]
        parts = element.split(None, 1)
        sd_id = parts[0] if parts else ""
        params: dict[str, str] = {}
        if len(parts) > 1:
            for match in SD_PARAM_RE.finditer(parts[1]):
                params[match.group("key")] = _unescape(match.group("value"))
        sd[sd_id] = params
        i = j + 1
    message = text[i:]
    if message.startswith(" "):
        message = message[1:]
    if message.startswith("\ufeff"):
        message = message[1:]
    return sd, message, True


def _parse_iso8601(value: str) -> datetime | None:
    if value in ("", "-"):
        return None
    candidate = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_rfc3164_timestamp(
    ts_text: str, fraction: str | None, now: datetime
) -> datetime | None:
    """Parse ``Mmm dd hh:mm:ss`` and infer the year (RFC3164 has none)."""
    parts = ts_text.split()
    if len(parts) != 3:
        return None
    month = _MONTHS.get(parts[0])
    if month is None:
        return None
    try:
        day = int(parts[1])
        hour, minute, second = (int(part) for part in parts[2].split(":"))
        stamp = datetime(now.year, month, day, hour, minute, second, tzinfo=timezone.utc)
        if fraction:
            stamp = stamp.replace(microsecond=int(fraction.ljust(6, "0")[:6]))
    except ValueError:
        return None
    # A message from "the future" almost certainly belongs to the previous year
    # (e.g. logs received on Jan 2 stamped Dec 31).
    if stamp > now + timedelta(days=1):
        try:
            stamp = stamp.replace(year=now.year - 1)
        except ValueError:  # 29 Feb in a non-leap year — keep as-is
            pass
    return stamp


def _try_rfc5424(rest: str) -> dict | None:
    """Attempt to interpret ``rest`` (after PRI) as an RFC5424 payload."""
    version_match = RFC5424_VERSION_RE.match(rest)
    if not version_match:
        return None
    version = int(version_match.group("version"))
    if version < 1 or version > 99:
        return None
    body = rest[version_match.end() :]
    # TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA [MSG]
    fields = body.split(" ", 5)
    if len(fields) < 6:
        return None
    timestamp_text, hostname, app_name, procid, msgid, remainder = fields
    structured_data, message, ok = _parse_structured_data(remainder)
    if not ok:
        return None
    return {
        "version": version,
        "timestamp": _parse_iso8601(timestamp_text),
        "hostname": None if hostname == "-" else hostname,
        "app_name": None if app_name == "-" else app_name,
        "procid": None if procid == "-" else procid,
        "msgid": None if msgid == "-" else msgid,
        "structured_data": structured_data,
        "message": message,
    }


def _split_rfc3164_body(body: str) -> tuple[str | None, str]:
    """Split ``hostname: MSG`` / ``hostname proc: MSG`` / ``%CISCO-MSG``."""
    body = body.lstrip()
    if body.startswith("%"):
        return None, body
    first, separator, remainder = body.partition(" ")
    if not separator:
        if body.endswith(":"):
            return body[:-1], ""
        return None, body
    if first.endswith(":"):
        # Cisco style: "rtr1: %LINK-3-UPDOWN: ..."
        return first[:-1], remainder.lstrip()
    # BSD style: "mymachine sshd[123]: message ..."
    return first, remainder


def _try_rfc3164(rest: str, now: datetime) -> dict | None:
    """Attempt to interpret ``rest`` (after PRI) as an RFC3164 payload."""
    match = RFC3164_TIMESTAMP_RE.match(rest)
    if not match:
        return None
    timestamp = _build_rfc3164_timestamp(match.group("ts"), match.group("frac"), now)
    if timestamp is None:
        return None
    hostname, message = _split_rfc3164_body(match.group("rest"))
    return {"timestamp": timestamp, "hostname": hostname, "message": message}


def parse_syslog(data: bytes | str, now: datetime | None = None) -> ParsedSyslog:
    """Parse one syslog message.

    Raises:
        ValueError: when the message is empty after decoding/trimming.
    """
    now = now or datetime.now(timezone.utc)
    text = (
        data.decode("utf-8", errors="replace")
        if isinstance(data, (bytes, bytearray))
        else data
    )
    text = text.replace("\x00", "").rstrip("\r\n")
    if not text.strip():
        raise ValueError("empty syslog message")

    pri: int | None = None
    facility: int | None = None
    severity: int | None = None
    pri_match = PRI_RE.match(text)
    rest = text
    if pri_match:
        candidate = int(pri_match.group("pri"))
        if candidate <= 191:
            pri = candidate
            facility = candidate // 8
            severity = candidate % 8
        rest = text[pri_match.end() :]

    parsed_5424 = _try_rfc5424(rest)
    if parsed_5424 is not None:
        return ParsedSyslog(
            raw=text,
            rfc="5424",
            pri=pri,
            facility=facility,
            severity=severity,
            timestamp=parsed_5424["timestamp"],
            hostname=parsed_5424["hostname"],
            app_name=parsed_5424["app_name"],
            procid=parsed_5424["procid"],
            msgid=parsed_5424["msgid"],
            structured_data=parsed_5424["structured_data"],
            message=parsed_5424["message"],
        )

    parsed_3164 = _try_rfc3164(rest, now)
    if parsed_3164 is not None:
        return ParsedSyslog(
            raw=text,
            rfc="3164",
            pri=pri,
            facility=facility,
            severity=severity,
            timestamp=parsed_3164["timestamp"],
            hostname=parsed_3164["hostname"],
            message=parsed_3164["message"],
        )

    # Vendor-specific formats (e.g. FortiGate "date=... devname=...") are kept
    # verbatim; normalization extracts hostname/vendor from key=value pairs.
    return ParsedSyslog(
        raw=text,
        rfc="raw",
        pri=pri,
        facility=facility,
        severity=severity,
        message=rest.strip(),
    )
