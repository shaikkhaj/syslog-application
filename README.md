# Network Syslog Monitoring & Intelligent Incident Correlation Platform

Production-style platform that receives syslog from network devices (Cisco, FortiGate,
Juniper, Linux), normalizes events into a common format, stores them in PostgreSQL, and —
in later phases — correlates them into incidents with root-cause analysis, topology-aware
recommendations, health scoring, anomaly detection and an AI troubleshooting assistant.

> **Status: Phase 5 complete** — ingestion + detection + incident correlation + network topology + **advanced RCA & network health**.
> ML/AI anomaly detection and auth/RBAC arrive in later phases (see [Roadmap](#roadmap)).

---

## Phase 5 architecture

```
 Devices (Cisco / FortiGate / Juniper / Linux)
        │  syslog UDP/TCP 514            (TLS 6514 reserved for a later phase)
        ▼
 ┌───────────────────────────── Backend (FastAPI) ─────────────────────────────┐
 │  SyslogListenerManager → IngestionPipeline → parse/normalize/store          │
 │                                      │                                      │
 │        DetectionEngine (10 rules) ────┤ alerts (dedupe by key)               │
 │                                      ▼                                      │
 │        CorrelationEngine (7 match rules, configurable window/weights)       │
 │          same key · device+interface · device+type · device+subsystem       │
 │          causal chain · shared endpoint (source/destination) · cross-device │
 │          → incidents (one active incident per correlation_key)              │
 │          → scoring (volume/severity/frequency/device importance/type/duration)
 │          → ranked root causes (deterministic, evidence-linked, no LLM)      │
 │          → state machine OPEN→INVESTIGATING→ACKNOWLEDGED→RESOLVED→CLOSED    │
 │          → timeline (creation, alerts, events, transitions, recovery)       │
 │  │                                                                          │
 │  │  Topology: devices + interface links → GET /topology (nodes/links)       │
 │  │  highlighted from open alerts + active incidents (max severity/node)     │
 │  │  device CRUD + link CRUD (interface-to-interface)                        │
 │  │  Health: GET /network-health → 0–100 score/band per device + overall     │
 │  │  RCA: GET /incidents/{id}/rca → culprit ranking + upstream dependencies  │
 │                                                                             │
 │  REST: /health · /events · /devices · /alerts · /incidents · /topology      │
 │  WebSocket: /api/v1/ws/alerts (alert + incident frames)                     │
 └─────────────────────────────────────────────────────────────────────────────┘
        │                                        │
        ▼                                        ▼
 PostgreSQL 16 (events, devices,            React dashboard: incidents panel
 interfaces, event_types, alerts,           (score, root cause + confidence,
 incidents, incident_alerts,                ack/resolve/close, timeline),
 incident_events, incident_state_history,   alerts panel, live events,
 topology_links)                            interactive topology map, RCA/health panels
```

Design notes:

- **Correlation dimensions** (all weights and the time window are env-configurable):
  identical correlation key, same device + interface, same device + event type,
  same device + subsystem, causal chains (INTERFACE_DOWN + unreachable/route/VPN …),
  shared endpoints (BGP neighbor / unreachable target across devices) and a
  cross-device same-type hint that only counts together with another dimension.
- **Duplicate-incident prevention**: a partial unique index allows at most ONE
  active (not RESOLVED/CLOSED) incident per `correlation_key`; concurrent
  creation races fall back to attaching the alert to the winning incident.
- **Root-cause ranking** is deterministic: candidate causes (upstream ISP outage,
  interface failure, BGP/OSPF peer failure, VPN, brute force, resource exhaustion,
  config change, path reachability, route instability) are scored from the
  incident's alert mix, ranked by confidence, and stored with their evidence.
- **Timeline** merges state-history rows (creation/ack/resolve/close), related
  alerts (recovery signals flagged) and the triggering syslog events, sorted
  chronologically.
- **Topology highlighting** is derived, not stored: `GET /api/v1/topology` marks
  nodes with open alerts or active incidents as `affected` and computes the
  maximum severity for colouring; links inherit severity from an endpoint in an
  active incident, an endpoint with open alerts, or an alert whose
  `context.interface` matches one of the link's interface names. Devices carry a
  `device_type` (router/switch/firewall/server) and links are explicit
  interface-to-interface rows (`topology_links`).
- **Severity**: incident scale LOW < MEDIUM < HIGH < CRITICAL (alert INFO maps
  to LOW); severity escalates as more severe alerts join.
- **Scoring**: weighted mix of alert count, max severity, alert frequency,
  device importance (hostname keywords), event-type weight and duration.
- **Real-time**: correlation runs inside the ingestion worker; created/updated/
  status-changed incident frames are broadcast on the WebSocket after commit.
- **Network health & RCA (Phase 5)**: device scores (0–100, banded
  healthy/degraded/critical) are derived at query time from open alerts, active
  incidents, recent-event volume and device status — nothing is stored. The RCA
  endpoint reuses Phase 3 root-cause candidates, ranks culprit devices with
  fixed explainable bonuses (severity, primary-failure vs consequence, topology
  adjacency, incident-primary, criticality) and walks upstream dependencies
  toward the core (BFS, ≤3 hops, only to devices one tier closer to the core).

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
│   │   │                       # syslog_events, incidents, alerts, topology_links
│   │   ├── schemas/            # Pydantic response models
│   │   ├── syslog/             # parser, normalize, framing, listeners,
│   │   │                       # event-type catalog, pipeline
│   │   ├── detection/          # Phase 2: types/enums, config, engine,
│   │   │   │                   #   alert service (dedupe), rule registry
│   │   │   └── rules/          # interface, routing, auth, performance, system
│   │   ├── correlation/        # Phase 3: match rules, scoring, root-cause
│   │   │   │                   #   ranking, incident engine + lifecycle
│   │   ├── health/             # Phase 5: health scoring, shared queries,
│   │   │   │                   #   RCA ranking + upstream dependencies
│   │   ├── realtime/           # thread-safe WebSocket broadcaster
│   │   ├── services/           # persistence (upserts)
│   │   └── api/v1/             # health, events, devices, alerts, incidents, topology, network-health, ws
│   └── tests/                  # 168 unit/integration tests
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

## API reference (Phase 5)

| Method | Path                  | Description |
|--------|-----------------------|-------------|
| GET    | `/api/v1/health`      | App status; DB/Redis, listener, pipeline, detection and correlation checks |
| GET    | `/api/v1/events`      | Events with `limit, offset, severity, hostname, device_ip, event_type, rfc, q, since, until` |
| GET    | `/api/v1/events/{id}` | Single event (404 if missing) |
| GET    | `/api/v1/devices`     | Discovered devices with event counts |
| POST   | `/api/v1/devices`     | Create a device (`hostname, ip_address, device_type, status, vendor`) |
| PATCH  | `/api/v1/devices/{id}`| Edit a device |
| DELETE | `/api/v1/devices/{id}`| Delete a device (204) |
| GET    | `/api/v1/event-types` | Event type catalog |
| GET    | `/api/v1/alerts`      | Alerts with `status, severity, event_type, device_id, q, since, until, limit, offset` |
| GET    | `/api/v1/alerts/{id}` | Alert detail + device + triggering event |
| POST   | `/api/v1/alerts/{id}/acknowledge` | Acknowledge (`{"actor": "..."}` optional) — 409 if resolved |
| POST   | `/api/v1/alerts/{id}/resolve`     | Resolve — 409 if already resolved |
| GET    | `/api/v1/incidents`   | Incidents with `status, severity, category, device_id, min_score, q, since, until` |
| GET    | `/api/v1/incidents/{id}` | Incident detail + related alerts |
| POST   | `/api/v1/incidents/{id}/acknowledge` | OPEN/INVESTIGATING → ACKNOWLEDGED (idempotent) |
| POST   | `/api/v1/incidents/{id}/resolve`     | → RESOLVED (409 when already terminal) |
| POST   | `/api/v1/incidents/{id}/close`       | RESOLVED → CLOSED (409 otherwise) |
| GET    | `/api/v1/incidents/{id}/timeline`    | Chronological creation/alerts/events/transitions |
| GET    | `/api/v1/incidents/{id}/rca` | RCA report — ranked culprit devices with reasons, candidate causes, upstream dependencies |
| GET    | `/api/v1/topology`   | Topology graph — nodes (devices + alert/incident highlighting) and links |
| GET    | `/api/v1/network-health` | Device health scores (0–100 + band) and overall network score (`limit`, `device_id`) |
| POST   | `/api/v1/links`      | Create an interface-to-interface link (201) |
| PATCH  | `/api/v1/links/{id}` | Edit a link |
| DELETE | `/api/v1/links/{id}` | Delete a link (204) |
| WS     | `/api/v1/ws/alerts`   | `{"type": "alert"\|"incident", "action": …}` frames |
| GET    | `/api/docs`           | Swagger UI (also `/api/redoc`) |

---

## Database schema

| Table          | Purpose |
|----------------|---------|
| `event_types`  | Canonical classification taxonomy (incl. `VPN_DISCONNECT`) + patterns, seeded/pruned at startup |
| `devices`      | Auto-registered devices keyed by source IP (+ `device_type` router/switch/firewall/server for topology) |
| `interfaces`   | Interfaces discovered in payloads (unique per device+name) |
| `topology_links` | **Phase 4** — interface-to-interface links between devices (status up/down; unique per endpoint pair, endpoint order-insensitive) |
| `syslog_events`| Normalized events |
| `alerts`       | Dedupe key, severity scale, status lifecycle, rule context JSON, ack/resolve audit fields |
| `incidents`    | **Active (Phase 3)** — correlation key (+ partial unique index for one ACTIVE incident per key), FSM status, severity, score, affected devices JSON, ranked root-cause candidates JSON, confidence, ack/resolve/close audit fields |
| `incident_alerts` | Join: alerts aggregated into an incident (unique per alert) |
| `incident_events` | Join: syslog events related to an incident (timeline source) |
| `incident_state_history` | Append-only audit of lifecycle transitions (timeline source) |

Tables are created idempotently at startup (`Base.metadata.create_all`); Alembic
migrations are planned for a later phase — Phase 4's `device_type` column and
`topology_links` table ship as an idempotent ALTER shim in `init_db.py`.

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

**Current results: `168 passed`** covering:

- `test_parser.py` — RFC3164/RFC5424/raw parsing, PRI edge cases, year rollover
- `test_framing.py` — RFC 6587 newline + octet-counted framing
- `test_normalize.py` — vendor detection, interface extraction, taxonomy
- `test_ingestion.py` — end-to-end store, upserts, catalog seeding
- `test_api.py` / `test_alerts_api.py` — health (incl. detection + correlation
  checks), event/alert filtering, detail, acknowledge/resolve flows, 409s,
  WebSocket streaming of created alerts
- `test_rules_*.py` (5 files) — every detection rule with realistic
  Cisco/FortiGate/Juniper/Linux samples and configurable thresholds
- `test_detection_engine.py` — registry, error isolation, dedupe/escalation,
  alert+incident payload chaining
- `test_correlation_scenarios.py` — **link failure, link flap, BGP failure,
  OSPF failure, ISP outage (2 devices, shared peer), and the requirement-8
  multi-type example (INTERFACE_DOWN + unreachable + route + VPN = 1 incident)**
- `test_correlation_scoring.py` — scoring factors, root-cause ranking,
  individual correlation rules
- `test_correlation_engine.py` — duplicate-incident prevention, time-window
  expiry, resolved-incident re-opening, disabled mode
- `test_incident_lifecycle.py` — state machine transitions +409-class errors,
  history audit, timeline content/ordering, persisted key/score/root cause
- `test_incident_api.py` — incident list/filters, detail, ack/resolve/close
  lifecycle, timeline endpoint, **WebSocket incident frames**
- `test_topology.py` — topology graph + open-alert/active-incident highlighting,
  device CRUD, link CRUD (12 tests)
- `test_network_health.py` — health scoring bands, RCA device ranking,
  RCA + network-health API responses (21 tests)

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
| `CORRELATION_ENABLED` | `true` | Master switch for the correlation engine |
| `CORRELATION_WINDOW_SECONDS` | `300` | Related alerts inside this window group into one incident |
| `CORRELATION_MIN_MATCH_SCORE` | `3.0` | Summed rule weight required to join an existing incident |
| `CORRELATION_WEIGHT_*` | see `.env.example` | Per-rule match weights (key, interface, type, subsystem, causal chain, shared endpoint, cross-device) |
| `CORRELATION_CRITICAL_DEVICE_KEYWORDS` | `core,edge,…` | Hostname keywords that boost incident scores |
| `CORRELATION_SCORE_*` | see `.env.example` | Incident scoring weights (alerts, severity, frequency, importance, type, duration) |

---

## Roadmap

- **Phase 1** ✅ Foundation + syslog ingestion (UDP/TCP, parsing, normalization, schema,
  APIs, dashboard, tests)
- **Phase 2** ✅ Detection engine — classification taxonomy, pluggable rules (interface,
  link-flap windows, BGP/OSPF state transitions, auth thresholds, config, CPU/memory,
  route changes, unreachability, VPN), alert dedupe/lifecycle, alerts API, WebSocket push
- **Phase 3** ✅ Correlation engine — 7 correlation rules (key/device/interface/type/
  subsystem/causal-chain/shared-endpoint/cross-device), temporal windows, duplicate
  prevention, incident FSM (OPEN→INVESTIGATING→ACKNOWLEDGED→RESOLVED→CLOSED), scoring,
  ranked root causes with evidence, timeline, incidents API + WebSocket + dashboard panel
- **Phase 4** ✅ Network topology — device/link models + CRUD, topology graph API
  with alert/incident highlighting, interactive SVG topology dashboard; ISP link
  uptime/downtime/flap stats remain open for a later phase
- **Phase 5** ✅ Advanced RCA + network health — device health scores (0–100,
  healthy/degraded/critical bands from alerts/incidents/events/status),
  `GET /network-health` + dashboard health panel, `GET /incidents/{id}/rca`
  culprit-device ranking with upstream dependencies, RCA block in the incidents
  panel, health badges on the topology map
- **Phase 6** Anomaly detection (scikit-learn) + alerting (email/web) + WebSocket push
- **Phase 7** Auth/RBAC/audit logs, reports & export, AI troubleshooting assistant
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
