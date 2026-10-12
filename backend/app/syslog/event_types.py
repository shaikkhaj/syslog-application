"""Event-type catalog: seeds, matching patterns and the resolver.

Classification happens once, at ingestion time, using regular expressions
over the normalized message. The canonical code list lives in
``app.detection.types.EventType``; the detection engine's rules then consume
these classifications to raise alerts (windows/thresholds are applied there,
never in the catalog).
"""

from __future__ import annotations

import re
import threading

from app.detection.types import EventType

# Order matters: the first matching entry wins, so the most specific rules
# come first. `patterns` are compiled with re.IGNORECASE.
EVENT_TYPE_SEEDS: list[dict] = [
    {
        "code": EventType.LINK_FLAP.value,
        "name": "Interface Flapping",
        "category": "interface",
        "description": "Interface repeatedly transitions between up and down.",
        "patterns": [r"\bflapping\b", r"\bflap(?:ped|s)?\b"],
    },
    {
        "code": EventType.BGP_DOWN.value,
        "name": "BGP Session Down",
        "category": "routing",
        "description": "BGP peer reset, dropped or moved to a non-established state.",
        "patterns": [
            r"BGP.{0,140}\b(?:reset|down|closed|ceased|notification|unusable|error)\b",
            r"ADJCHANGE.{0,80}\bDown\b",
            r"peer.{0,80}moved state.{0,40}to\s+(?:Idle|Active)",
        ],
    },
    {
        "code": EventType.BGP_UP.value,
        "name": "BGP Session Established",
        "category": "routing",
        "description": "BGP peer moved to the Established state.",
        "patterns": [
            r"ADJCHANGE.{0,80}\bUp\b",
            r"BGP.{0,140}\bEstablished\b",
            r"moved state.{0,60}to\s+Established",
        ],
    },
    {
        "code": EventType.OSPF_NEIGHBOR_DOWN.value,
        "name": "OSPF Neighbor Down",
        "category": "routing",
        "description": "OSPF adjacency moved from Full to Down.",
        "patterns": [
            r"OSPF.{0,160}from\s+Full\s+to\s+Down",
            r"Nbr.{0,80}from\s+Full\s+to\s+Down",
            r"OSPF.{0,140}adjacency.{0,60}\b(?:down|failed)\b",
        ],
    },
    {
        "code": EventType.OSPF_NEIGHBOR_UP.value,
        "name": "OSPF Neighbor Up",
        "category": "routing",
        "description": "OSPF adjacency established (Down to Full).",
        "patterns": [
            r"OSPF.{0,160}from\s+Down\s+to\s+Full",
            r"OSPF.{0,140}adjacency.{0,60}\b(?:up|established)\b",
        ],
    },
    {
        "code": EventType.DEVICE_UNREACHABLE.value,
        "name": "Device / Host Unreachable",
        "category": "system",
        "description": "A host or network path is reported unreachable.",
        "patterns": [
            r"\bno route to host\b",
            r"\bhost unreachable\b",
            r"\b(?:network|host)\s+is\s+unreachable\b",
            r"\bdevice unreachable\b",
            r"\bnot\s+reachable\b",
            r"\bpath\s+(?:expected\s+)?unreachable\b",
        ],
    },
    {
        "code": EventType.VPN_DISCONNECT.value,
        "name": "VPN / Tunnel Down",
        "category": "system",
        "description": "An IPSec/VPN tunnel disconnected or went down.",
        "patterns": [
            r"\bipsec tunnel[^\n]{0,60}\bdown\b",
            r"\btunnel[^\n]{0,40}\b(?:is\s+)?down\b",
            r"\bvpn[^\n]{0,60}\b(?:disconnect|down|closed|failed)\b",
            r"\btunnel[^\n]{0,60}\b(?:disconnect|closed)\b",
        ],
    },
    {
        "code": EventType.INTERFACE_DOWN.value,
        "name": "Interface Down",
        "category": "interface",
        "description": "Interface or line protocol changed state to down.",
        "patterns": [
            r"changed state to down",
            r"interface\s+[^\n]{0,60}\bis\s+down\b",
            r"\blink\s+(?:is\s+)?down\b",
        ],
    },
    {
        "code": EventType.INTERFACE_UP.value,
        "name": "Interface Up",
        "category": "interface",
        "description": "Interface or line protocol changed state to up.",
        "patterns": [
            r"changed state to up",
            r"interface\s+[^\n]{0,60}\bis\s+up\b",
            r"\blink\s+(?:is\s+)?up\b",
        ],
    },
    {
        "code": EventType.CPU_HIGH.value,
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
        "code": EventType.MEMORY_HIGH.value,
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
        "code": EventType.AUTH_FAILURE.value,
        "name": "Authentication Failure",
        "category": "security",
        "description": "Login or authentication failure detected.",
        "patterns": [
            r"\blogin[-\s]failed\b",
            r"\bfailed password\b",
            r"\bauthentication failed\b",
            r"\bLOGIN_FAILED\b",
            r"\binvalid user\b",
            r"auth[^\n]{0,40}\bfail",
        ],
    },
    {
        "code": EventType.CONFIG_CHANGE.value,
        "name": "Configuration Change",
        "category": "configuration",
        "description": "Device configuration was modified or committed.",
        "patterns": [
            r"configured from",
            r"\bUI_COMMIT",
            r"configuration[^\n]{0,60}\b(?:chang|updat)",
            r"\bconfig(?:uration)?[^\n]{0,60}\b(?:chang|updat)",
            r"\bcommit\s+(?:complete|completed|done)\b",
        ],
    },
    {
        "code": EventType.ROUTE_CHANGE.value,
        "name": "Route Change",
        "category": "routing",
        "description": "A routing table entry was added, removed or changed.",
        "patterns": [
            r"\bRTM_(?:NEW|DEL)\b",
            r"%IPRT-\d+",
            r"\broute\s+(?:add(?:ed)?|delet(?:e|ed)|chang(?:e|ed)|remov(?:e|ed)|install(?:ed)?)\b",
            r"\bstatic route\b[^\n]{0,60}\b(?:chang|add|delet|remov)",
        ],
    },
    {
        "code": EventType.INTERFACE_ERROR.value,
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
        "code": EventType.SYSTEM_RESTART.value,
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
        "code": EventType.OTHER.value,
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
        """Return the event type code for a message (OTHER when unmatched)."""
        for code, pattern in self._compiled:
            if pattern.search(message):
                return code
        return EventType.OTHER.value

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
