"""Normalization of parsed syslog messages into a common event format."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.syslog.event_types import resolver
from app.syslog.parser import ParsedSyslog

SEVERITY_LABELS = {
    0: "emergency",
    1: "alert",
    2: "critical",
    3: "error",
    4: "warning",
    5: "notice",
    6: "info",
    7: "debug",
}

FACILITY_NAMES = {
    0: "kern", 1: "user", 2: "mail", 3: "daemon", 4: "auth", 5: "syslog",
    6: "lpr", 7: "news", 8: "uucp", 9: "cron", 10: "authpriv", 11: "ftp",
    12: "ntp", 13: "audit", 14: "alert", 15: "clock", 16: "local0",
    17: "local1", 18: "local2", 19: "local3", 20: "local4", 21: "local5",
    22: "local6", 23: "local7",
}

# First matching vendor wins; patterns are matched against
# "<app_name> <hostname> <message>" as one haystack (IGNORECASE).
VENDOR_PATTERNS: list[tuple[str, list[re.Pattern[str]]]] = [
    ("fortinet", [
        re.compile(r"\bdevname=", re.I),
        re.compile(r"\bdevid=", re.I),
        re.compile(r"fortigate", re.I),
        re.compile(r"\blogid=\d+", re.I),
    ]),
    ("cisco", [
        re.compile(r"%(?:LINK|LINEPROTO|SYS|SEC_LOGIN|BGP|OSPF|DUAL)-\d+-", re.I),
        re.compile(r"cisco\s+ios", re.I),
        re.compile(r"\bIOS(?:XE)?\b"),
    ]),
    ("juniper", [
        re.compile(r"\bJUNOS\b", re.I),
        re.compile(r"\brpd\b"),
        re.compile(r"%?MGD[_-]", re.I),
        re.compile(r"\bRT_(?:FLOW|SECURITY|UNSOLICITED)\b", re.I),
        re.compile(r"\bbfdd\b"),
        re.compile(r"\bfpc\d", re.I),
        re.compile(r"\b(?:ge|xe|fe|et)-\d+/\d+/\d+\b"),
    ]),
    ("linux", [
        re.compile(r"\bsystemd\b", re.I),
        re.compile(r"\bsshd\b", re.I),
        re.compile(r"\bsudo\b", re.I),
        re.compile(r"\bCRON\b"),
        re.compile(r"\bkernel\b", re.I),
    ]),
]

# Interface name extraction — first matching pattern wins.
INTERFACE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"Interface\s+([A-Za-z][\w./-]*)"),           # Cisco / IOS-XE
    re.compile(r'interface="([^"]+)"'),                       # FortiGate
    re.compile(r"\biface=([\w.-]+)"),
    re.compile(r"\binterface\s+([A-Za-z][\w./-]+)\b", re.I),
    re.compile(r"\b[a-z]{2,4}-\d+/\d+/\d+\b"),                # Juniper IFL
]

_DEVNAME_RE = re.compile(r'devname="([^"]+)"', re.I)


@dataclass
class NormalizedEvent:
    """Common event format produced by the normalization stage."""

    rfc: str
    pri: int | None
    facility: int | None
    facility_name: str | None
    severity: int | None
    severity_label: str | None
    timestamp: datetime | None
    received_at: datetime
    hostname: str | None
    app_name: str | None
    procid: str | None
    msgid: str | None
    vendor: str
    source_ip: str
    interface_name: str | None
    event_type_code: str
    message: str
    raw_message: str
    structured_data: dict | None


def detect_vendor(parsed: ParsedSyslog) -> str:
    """Best-effort vendor detection from message content and header fields."""
    haystack = " ".join(
        part for part in (parsed.app_name, parsed.hostname, parsed.message) if part
    )
    for vendor, patterns in VENDOR_PATTERNS:
        if any(pattern.search(haystack) for pattern in patterns):
            return vendor
    return "unknown"


def extract_interface(message: str) -> str | None:
    """Extract an interface name from a message, if one is present."""
    for pattern in INTERFACE_PATTERNS:
        match = pattern.search(message)
        if match:
            # Group 1 exists for patterns with a capture group; whole-match
            # patterns (e.g. Juniper "ge-0/0/0") return the match itself.
            name = match.group(1) if match.lastindex else match.group(0)
            return name.strip()
    return None


def _fallback_hostname(vendor: str, message: str) -> str | None:
    if vendor == "fortinet":
        match = _DEVNAME_RE.search(message)
        if match:
            return match.group(1)
    return None


def normalize(
    parsed: ParsedSyslog,
    source_ip: str,
    received_at: datetime | None = None,
) -> NormalizedEvent:
    """Convert a :class:`ParsedSyslog` into the platform's common event format."""
    received_at = received_at or datetime.now(timezone.utc)
    vendor = detect_vendor(parsed)
    hostname = parsed.hostname or _fallback_hostname(vendor, parsed.message)
    severity = parsed.severity
    facility = parsed.facility
    return NormalizedEvent(
        rfc=parsed.rfc,
        pri=parsed.pri,
        facility=facility,
        facility_name=FACILITY_NAMES.get(facility) if facility is not None else None,
        severity=severity,
        severity_label=SEVERITY_LABELS.get(severity) if severity is not None else None,
        timestamp=parsed.timestamp,
        received_at=received_at,
        hostname=hostname,
        app_name=parsed.app_name,
        procid=parsed.procid,
        msgid=parsed.msgid,
        vendor=vendor,
        source_ip=source_ip,
        interface_name=extract_interface(parsed.message),
        event_type_code=resolver.resolve_code(parsed.message),
        message=parsed.message,
        raw_message=parsed.raw,
        structured_data=parsed.structured_data,
    )
