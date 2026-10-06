"""Event-type catalog: seeds, matching patterns and the resolver.

Phase 1 performs simple rule-based classification at ingestion time using
regular expressions over the normalized message. The full detection engine
(link-flap windows, thresholds, ML anomaly scores, ...) arrives in later
phases — the catalog table and resolver are already in place for it.
"""

from __future__ import annotations

import re
import threading

# Order matters: the first matching entry wins, so the most specific rules
# come first. `patterns` are compiled with re.IGNORECASE.
EVENT_TYPE_SEEDS: list[dict] = [
    {
        "code": "link_flap",
        "name": "Interface Flapping",
        "category": "interface",
        "description": "Interface repeatedly transitions between up and down.",
        "patterns": [r"\bflapping\b", r"\bflap(?:ped|s)?\b"],
    },
    {
        "code": "bgp_down",
        "name": "BGP Session Down",
        "category": "routing",
        "description": "BGP peer reset, dropped or moved to a non-established state.",
        "patterns": [
            r"BGP.{0,120}\b(?:reset|down|closed|ceased|notification|unusable)\b",
            r"ADJCHANGE.{0,80}\bDown\b",
            r"peer.{0,80}moved state.{0,40}to\s+(?:Idle|Active|Idle \()",
        ],
    },
    {
        "code": "bgp_up",
        "name": "BGP Session Established",
        "category": "routing",
        "description": "BGP peer moved to the Established state.",
        "patterns": [
            r"ADJCHANGE.{0,80}\bUp\b",
            r"BGP.{0,120}\bEstablished\b",
            r"peer.{0,80}moved state.{0,40}to\s+Established",
        ],
    },
    {
        "code": "ospf_neighbor_change",
        "name": "OSPF Neighbor Change",
        "category": "routing",
        "description": "OSPF neighbor state changed (down, full, adjacency issue).",
        "patterns": [
            r"OSPF.{0,120}neighbor.{0,120}\b(?:down|up|change|state)\b",
            r"Neighbor.{0,80}state\s+(?:Down|Full|Init|2-Way)",
        ],
    },
    {
        "code": "link_down",
        "name": "Interface Link Down",
        "category": "interface",
        "description": "Interface or line protocol changed state to down.",
        "patterns": [
            r"changed state to down",
            r"interface\s+\S+\s+is\s+down",
            r"\blink\s+(?:is\s+)?down\b",
        ],
    },
    {
        "code": "link_up",
        "name": "Interface Link Up",
        "category": "interface",
        "description": "Interface or line protocol changed state to up.",
        "patterns": [
            r"changed state to up",
            r"interface\s+\S+\s+is\s+up",
            r"\blink\s+(?:is\s+)?up\b",
        ],
    },
    {
        "code": "high_cpu",
        "name": "High CPU Utilization",
        "category": "performance",
        "description": "CPU utilization crossed the configured threshold.",
        "patterns": [
            r"cpu[_\s]?(?:utilization|usage|load|idle)[^\n]{0,80}?(?:[89]\d|100)\s?%",
            r"cpu[^\n]{0,60}\b(?:threshold|high)\b",
            r"\bhigh cpu\b",
        ],
    },
    {
        "code": "high_memory",
        "name": "High Memory Utilization",
        "category": "performance",
        "description": "Memory utilization crossed the configured threshold.",
        "patterns": [
            r"memory[_\s]?(?:usage|utilization|fullness)[^\n]{0,80}?(?:[89]\d|100)\s?%",
            r"\bout of memory\b",
            r"\bhigh memory\b",
            r"memory[^\n]{0,60}\bthreshold\b",
        ],
    },
    {
        "code": "auth_failure",
        "name": "Authentication Failure",
        "category": "security",
        "description": "Login or authentication failure detected.",
        "patterns": [
            r"\blogin failed\b",
            r"\bfailed password\b",
            r"\bauthentication failed\b",
            r"\bLOGIN_FAILED\b",
            r"\binvalid user\b",
            r"auth[^\n]{0,40}\bfail",
        ],
    },
    {
        "code": "config_change",
        "name": "Configuration Change",
        "category": "configuration",
        "description": "Device configuration was modified or committed.",
        "patterns": [
            r"configured from",
            r"\bUI_COMMIT",
            r"configuration\s+(?:change|updated|changed)",
            r"\bconfig(?:uration)?\s+(?:change|updated|changed)",
            r"\bcommit\s+(?:complete|completed|done)\b",
        ],
    },
    {
        "code": "interface_error",
        "name": "Interface Error",
        "category": "interface",
        "description": "Interface-level errors (CRC, input/output errors).",
        "patterns": [
            r"\binput errors?\b",
            r"\boutput errors?\b",
            r"\bCRC errors?\b",
            r"interface[^\n]{0,60}\berror",
        ],
    },
    {
        "code": "system_restart",
        "name": "System Restart / Reload",
        "category": "system",
        "description": "Device rebooted, reloaded or restarted.",
        "patterns": [
            r"\bsystem (?:restart|reboot|startup)\b",
            r"\breboot(?:ed)?\b",
            r"SYS-\d+-RESTART",
            r"\breload (?:command|initiated|completed)\b",
            r"\bcold start\b",
        ],
    },
    {
        "code": "other",
        "name": "Other Event",
        "category": "other",
        "description": "Event did not match any specific rule.",
        "patterns": [],
    },
]


class EventTypeResolver:
    """Thread-safe resolver mapping messages to event type code and DB id."""

    def __init__(self, seeds: list[dict] | None = None) -> None:
        seeds = seeds if seeds is not None else EVENT_TYPE_SEEDS
        self._compiled: list[tuple[str, re.Pattern[str]]] = [
            (seed["code"], re.compile(pattern, re.IGNORECASE))
            for seed in seeds
            for pattern in seed["patterns"]
        ]
        self._id_by_code: dict[str, int] | None = None
        self._lock = threading.Lock()

    def resolve_code(self, message: str) -> str:
        """Return the event type code for a message ('other' when unmatched)."""
        for code, pattern in self._compiled:
            if pattern.search(message):
                return code
        return "other"

    def get_id(self, session, code: str) -> int | None:
        """Return the catalog id for a code, loading the map once per process."""
        with self._lock:
            if self._id_by_code is None:
                from sqlalchemy import select

                from app.models.models import EventType

                rows = session.execute(select(EventType.id, EventType.code)).all()
                self._id_by_code = {code_: id_ for id_, code_ in rows}
        return self._id_by_code.get(code)

    def invalidate(self) -> None:
        """Drop the cached id map (used by tests when they reseed the DB)."""
        with self._lock:
            self._id_by_code = None


resolver = EventTypeResolver()
