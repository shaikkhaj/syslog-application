# Network Syslog Monitoring & Intelligent Incident Correlation Platform

Production-style platform that receives syslog from network devices (Cisco, FortiGate,
Juniper, Linux), normalizes events into a common format, stores them in PostgreSQL, and —
in later phases — correlates them into incidents with root-cause analysis, topology-aware
recommendations, health scoring, anomaly detection and an AI troubleshooting assistant.

> **Status: Phase 2 complete** — foundation + ingestion + **detection engine**.
> Correlation/topology, ML/AI, auth/RBAC arrive in later phases (see [Roadmap](#roadmap)).

---

## Phase 2 architecture

```
 Devices (Cisco / FortiGate / Juniper / Linux)
        │  syslog UDP/TCP 514            (TLS 6514 reserved for a later phase)
        ▼
 ┌───────────────────────────── Backend (FastAPI) ─────────────────────────────┐
 │  SyslogListenerManager                                                     │
 │    ├── UdpSyslogTransport ─┐                                                │
 │    └── TcpSyslogTransport ─┴─► IngestionPipeline (bounded queue,            │
 │                                 N worker threads)                           │
 │        parse (RFC3164/5424/raw) ─► normalize ─► store (device + event)      │
 │                                      │                                      │
 │                                      ▼                                      │
 │        DetectionEngine (pluggable rule registry, per-event evaluation)      │
 │          interface_state · link_flap(window/threshold) · bgp_state          │
 │          ospf_state · route_change · auth_failure_threshold                 │
 │          performance_threshold(cpu/mem) · config_change · device_unreachable│
 │                      │  dedupe by key: repeats coalesce into one alert      │
 │                      ▼                                                      │
 │        alerts (PostgreSQL) ──► REST API ──► WebSocket fan-out ──► Dashboard  │
 │                                                                             │
 │  REST API: /health · /events · /devices · /event-types · /alerts            │
 │  WebSocket: /api/v1/ws/alerts (real-time alert updates)                     │
 └─────────────────────────────────────────────────────────────────────────────┘
        │                                   │
        ▼                                   ▼
 PostgreSQL 16 (events, devices,       React + Tailwind dashboard
 interfaces, event_types, alerts,      (health card, alerts panel with
 incidents)   + Redis                   ack/resolve, filters, live events)
```

Design notes:

- **Classification once, detection many**: the `event_types` catalog tags every
  event at ingestion with a canonical uppercase code (`INTERFACE_DOWN`,
  `BGP_DOWN`, `AUTH_FAILURE`, `ROUTE_CHANGE`, …). Detection rules consume those
  classifications and apply windows/thresholds — never the other way around.
- **Pluggable rules**: new detections are added by creating a `DetectionRule`
  subclass and appending it to `DEFAULT_RULES` (`app/detection/rules/__init__.py`)
  — the pipeline and engine never change. A failing rule is isolated and counted;
  it can never break ingestion.
- **Alert dedupe**: findings carry a `dedupe_key` (type + device + interface /
  neighbor / attacker). While an open alert with the same key exists, repeats
  coalesce (`event_count`, `last_seen_at`) and severity only escalates; resolving
  re-opens the key for a fresh alert.
- **Configurable thresholds**: link-flap window/threshold, auth-failure
  window/threshold, CPU/memory percent — all environment variables
  (`.env`), read through `DetectionConfig`.
- **Severities**: `INFO < LOW < MEDIUM < HIGH < CRITICAL` on alerts (distinct
  from raw syslog severity on events).
- **Real-time**: detection runs in worker threads and hops to the event loop via
  a thread-safe broadcaster; `WS /api/v1/ws/alerts` pushes `created`/`updated`
  frames. The dashboard also polls as a fallback.
- **Transports are pluggable** — TLS (port 6514) registers in
  `SyslogListenerManager` in a later phase (`SYSLOG_TLS_ENABLED` currently logs
  a warning — no fake implementation).

---

## Repository layout

```
log-applica/
├── docker-compose.yml          # db + redis + backend + frontend
├── .env / .env.example         # environment configuration
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py             # FastAPI app factory + lifespan
│   │   ├── core/               # config (pydantic-settings), logging
│   │   ├── db/                 # engine/session, init_db (retry + seed)
│   │   ├── models/             # event_types, devices, interfaces,
│   │   │                       # syslog_events, incidents, alerts
│   │   ├── schemas/            # Pydantic response models
│   │   ├── syslog/             # parser, normalize, framing, listeners,
│   │   │                       # event-type catalog, pipeline
│   │   ├── detection/          # Phase 2: types/enums, config, engine,
│   │   │   │                   #   alert service (dedupe), rule registry
│   │   │   └── rules/          # interface, routing, auth, performance, system
│   │   ├── realtime/           # thread-safe WebSocket broadcaster
│   │   ├── services/           # persistence (upserts)
│   │   └── api/v1/             # health, events, devices, alerts, ws routes
│   └── tests/                  # 101 unit/integration tests
├── frontend/
│   ├── Dockerfile              # multi-stage node build → nginx
│   ├── nginx.conf              # /api proxy → backend:8000
│   └── src/                    # React dashboard (components, pages, api)
└── tools/
    └── syslog_generator.py     # sample Cisco/FortiGate/Juniper/Linux sender
```

---

## Quick start (Docker)

Prerequisites: Docker with Compose v2.

```bash
# 1. Configure environment (defaults work out of the box)
cp .env.example .env

# 2. Build and start everything
docker compose up --build
```

Startup order is health-checked: PostgreSQL → Redis → backend (waits for DB, creates
tables, seeds the event-type catalog, binds UDP/TCP 514) → frontend.

| Service   | URL                          |
|-----------|------------------------------|
| Dashboard | http://localhost:3000        |
| REST API  | http://localhost:8000/api/v1 |
| Swagger   | http://localhost:8000/api/docs |
| Syslog    | UDP/TCP `localhost:514`      |

> **Windows/macOS note:** Docker Desktop maps container ports through its VM; if binding
> host port 514 fails or conflicts, change `SYSLOG_HOST_PORT` in `.env` (e.g. `5514`) —
> the container still listens on 514 internally.

---

## Sending test syslog messages

### 1. Sample generator (recommended)

```bash
# 20 mixed vendor messages over UDP
python tools/syslog_generator.py --host 127.0.0.1 --transport udp --count 20

# One vendor only, over TCP
python tools/syslog_generator.py --host 127.0.0.1 --transport tcp --scenario cisco

# If you changed SYSLOG_HOST_PORT to 5514:
python tools/syslog_generator.py --host 127.0.0.1 --port 5514 --count 40
```

Sample scenarios: `cisco`, `fortigate`, `juniper`, `linux`, `all` — covering link
up/down, BGP/OSPF changes, config commits, auth failures, high CPU/memory and traffic denials.

### 2. One-off raw messages

Linux/macOS:

```bash
logger -P14 -n 127.0.0.1 -p local6.info "test message from logger"

printf '<134>%s rtr1: %%LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down\n' \
  "$(date '+%b %-d %H:%M:%S')" | nc -u -w1 127.0.0.1 514
```

Windows PowerShell (UDP):

```powershell
$udp = New-Object System.Net.Sockets.UdpClient
$msg = [Text.Encoding]::ASCII.GetBytes('<134>Jan 15 10:23:45 rtr1: %LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down')
$udp.Send($msg, $msg.Length, '127.0.0.1', 514)
```

### 3. From a real device

Point the device at the collector: `logging host <collector-ip> transport tcp port 514`
(Cisco), `config sys log` → remote syslog server (FortiGate), `set host <ip>` (Juniper),
`/etc/rsyslog.conf` → `*.* @@collector:514` (Linux).

---

## Expected output

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

```json
{
  "status": "ok",
  "app": "Network Syslog Monitoring & Incident Correlation Platform",
  "version": "0.1.0",
  "environment": "development",
  "uptime_seconds": 42.1,
  "checks": {
    "database": {"status": "ok", "latency_ms": 0.31},
    "redis": {"status": "ok"},
    "syslog": {
      "status": "ok",
      "listeners": [
        {"name": "udp", "host": "0.0.0.0", "port": 514, "running": true,
         "messages_received": 21, "last_message_at": "2026-01-15T10:23:45+00:00"},
        {"name": "tcp", "host": "0.0.0.0", "port": 514, "running": true,
         "messages_received": 1, "last_message_at": null}
      ],
      "errors": {},
      "pipeline": {"submitted": 22, "stored": 22, "parse_errors": 0,
                   "failed": 0, "dropped": 0}
    }
  }
}
```

Events API:

```bash
curl "http://localhost:8000/api/v1/events?limit=5&severity=3"
```

```json
{
  "items": [
    {
      "id": 42,
      "received_at": "2026-01-15T10:23:46.120+00:00",
      "timestamp": "2026-01-15T10:23:45+00:00",
      "source_ip": "192.168.1.10",
      "rfc": "3164",
      "facility": 16,
      "severity": 3,
      "severity_label": "error",
      "hostname": "rtr-core-01",
      "vendor": "cisco",
      "interface_name": "GigabitEthernet0/1",
      "event_type_code": "link_down",
      "message": "%LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down",
      "raw_message": "<134>Jan 15 10:23:45 rtr-core-01: %LINK-3-UPDOWN: ..."
    }
  ],
  "total": 1,
  "limit": 5,
  "offset": 0
}
```

Dashboard: open **http://localhost:3000** — the health card shows `OK` for
Database/Redis/Syslog, and the event table fills in within ~5 seconds of sending messages
(auto-refresh). Backend logs (`docker compose logs -f backend`) show each received message.

---

## API reference (Phase 2)

| Method | Path                  | Description |
|--------|-----------------------|-------------|
| GET    | `/api/v1/health`      | App status, DB/Redis checks, listener + pipeline + detection counters |
| GET    | `/api/v1/events`      | Events with `limit, offset, severity, hostname, device_ip, event_type, rfc, q, since, until` |
| GET    | `/api/v1/events/{id}` | Single event (404 if missing) |
| GET    | `/api/v1/devices`     | Discovered devices with event counts |
| GET    | `/api/v1/event-types` | Event type catalog |
| GET    | `/api/v1/alerts`      | Alerts with `status, severity, event_type, device_id, q, since, until, limit, offset` |
| GET    | `/api/v1/alerts/{id}` | Alert detail + device + triggering event |
| POST   | `/api/v1/alerts/{id}/acknowledge` | Acknowledge (`{"actor": "..."}` optional) — 409 if resolved |
| POST   | `/api/v1/alerts/{id}/resolve`     | Resolve (`{"actor": "..."}` optional) — 409 if already resolved |
| WS     | `/api/v1/ws/alerts`   | Real-time `{"type": "alert", "action": "created"\|"updated", "alert": {...}}` frames |
| GET    | `/api/docs`           | Swagger UI (also `/api/redoc`) |

---

## Database schema

| Table          | Purpose |
|----------------|---------|
| `event_types`  | Canonical classification taxonomy (`INTERFACE_DOWN`, `BGP_DOWN`, `AUTH_FAILURE`, …) + regex patterns, seeded/pruned at startup |
| `devices`      | Auto-registered devices keyed by source IP (hostname, vendor, last seen) |
| `interfaces`   | Interfaces discovered in payloads (unique per device+name) |
| `syslog_events`| Normalized events: RFC variant, facility/severity, vendor, interface, event type, structured data |
| `alerts`       | **Active (Phase 2)** — dedupe key, severity scale, status lifecycle (`new → acknowledged → resolved`), rule context JSON, ack/resolve audit fields; `incident_id` reserved for Phase 3 |
| `incidents`    | Reserved for the correlation/RCA engine (later phase) |

Tables are created idempotently at startup (`Base.metadata.create_all`); Alembic
migrations are planned for Phase 3 when the schema starts evolving.

---

## Running tests

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows  —  source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt
pytest
```

Tests run against a throwaway SQLite database with listeners disabled — no Docker or
PostgreSQL required.

**Current results: `101 passed`** covering:

- `test_parser.py` — RFC3164 (Cisco/BSD, fractional seconds, year rollover), RFC5424
  (structured data, escaped quotes, NIL fields, malformed fallback), raw FortiGate format,
  invalid PRI, empty/invalid-UTF-8 input
- `test_framing.py` — newline and octet-counted TCP framing, split chunks, oversize discard
- `test_normalize.py` — vendor detection (4 vendors), interface extraction, severity/facility
  labels, event-type classification
- `test_ingestion.py` — end-to-end parse → normalize → store, device/interface upserts,
  catalog seeding
- `test_api.py` — health, event filtering (search/severity/IP/type), 404s, devices,
  validation errors
- `test_rules_interface.py` — INTERFACE_DOWN/UP alerts, coalescing, link-flap threshold
  (below/at), window expiry, configurable threshold/window
- `test_rules_routing.py` — BGP/OSPF down+up with neighbor extraction and previous-state
  tracking (Cisco + Juniper), route-change detection and coalescing
- `test_rules_auth.py` — threshold silence, crossing (MEDIUM), 3× escalation (HIGH),
  per-attacker separation, window expiry, configurable window/threshold, Cisco SEC_LOGIN
- `test_rules_performance.py` — CPU/memory threshold alerting, suppression below the
  configured percent, unknown-percent fallback, coalescing
- `test_rules_system.py` — config-change (Cisco/FortiGate/Linux actor extraction),
  unreachable (CRITICAL) with target extraction and coalescing
- `test_detection_engine.py` — taxonomy completeness, severity ordering, rule registry,
  rule-error isolation, disabled mode, dedupe/escalation/resolution flow, stats
- `test_alerts_api.py` — list/filter/pagination, validation 422s, detail with
  device+event, acknowledge/resolve lifecycle (409s), health detection check,
  **WebSocket streaming of created alerts**

Inside Docker: `docker compose exec backend pytest`.

---

## Configuration (`.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_*` / `DATABASE_URL` | see `.env.example` | Database connection (URL overrides parts) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis (health-checked; used by later phases) |
| `SYSLOG_LISTENERS_ENABLED` | `true` | Master switch for UDP/TCP listeners |
| `SYSLOG_UDP_PORT` / `SYSLOG_TCP_PORT` | `514` | Container-side listener ports |
| `SYSLOG_TLS_ENABLED` / `SYSLOG_TLS_PORT` | `false` / `6514` | Reserved for TLS transport |
| `SYSLOG_QUEUE_MAXSIZE` | `10000` | Ingestion queue bound (drops + counts when full) |
| `SYSLOG_WORKER_COUNT` | `4` | Ingestion worker threads |
| `SYSLOG_HOST_PORT` | `514` | Host-side published syslog port |
| `CORS_ORIGINS` | localhost:3000/5173 | Allowed frontend origins |
| `LOG_LEVEL` | `INFO` | Backend log level |
| `DETECTION_ENABLED` | `true` | Master switch for the detection engine |
| `LINK_FLAP_WINDOW_SECONDS` / `LINK_FLAP_THRESHOLD` | `300` / `4` | DOWN/UP transitions inside the window that raise one LINK_FLAP alert |
| `AUTH_FAILURE_WINDOW_SECONDS` / `AUTH_FAILURE_THRESHOLD` | `300` / `5` | Failed logins per device+attacker inside the window (MEDIUM; HIGH at 3×) |
| `CPU_HIGH_THRESHOLD_PERCENT` / `MEMORY_HIGH_THRESHOLD_PERCENT` | `90` / `90` | Utilization percent that raises/keeps a performance alert |

---

## Roadmap

- **Phase 1** ✅ Foundation + syslog ingestion (UDP/TCP, parsing, normalization, schema,
  APIs, dashboard, tests)
- **Phase 2** ✅ Detection engine — classification taxonomy, 9 pluggable rules (interface,
  link-flap windows, BGP/OSPF state transitions, auth thresholds, config, CPU/memory,
  route changes, unreachability), alert dedupe/lifecycle, alerts API, WebSocket push,
  dashboard alerts panel
- **Phase 3** Correlation + incidents — deduplication, incident lifecycle, RCA with
  confidence, recommendations
- **Phase 4** Topology + ISP link monitoring — uptime/downtime/flap stats,
  topology-aware correlation, health scores
- **Phase 5** Anomaly detection (scikit-learn) + alerting (email/web) + WebSocket push
- **Phase 6** Auth/RBAC/audit logs, reports & export, AI troubleshooting assistant
- TLS syslog transport (6514) and Alembic migrations — slotted into the phase where first
  needed

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `bind: permission denied` on port 514 (Linux) | Container runs as root by default; otherwise set `SYSLOG_HOST_PORT=5514` |
| Health `status: degraded`, redis `error` | Expected when Redis is not running (local runs); with compose it should be `ok` |
| No events in dashboard | Check `docker compose logs -f backend` for listener bind errors; verify the generator targets the published host port |
| Port 514 already in use | Change `SYSLOG_HOST_PORT` in `.env` and restart compose |
| Windows Firewall prompt on first run | Allow Docker/Python on private networks so devices can reach UDP 514 |
