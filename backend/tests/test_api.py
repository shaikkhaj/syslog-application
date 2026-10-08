"""API tests: health, events, devices, event-types endpoints."""

from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 api-rtr-01: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/2, changed state to down"
)
LINUX_AUTH = (
    b"<85>1 2026-01-15T10:23:47.003Z api-web01 sshd - - - "
    b"Failed password for invalid user admin from 203.0.113.10 port 54321 ssh2"
)


def test_health_endpoint(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    # Redis is intentionally unreachable in tests → degraded, DB must be ok.
    assert body["status"] in ("ok", "degraded")
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "error"
    assert body["checks"]["syslog"]["status"] in ("ok", "disabled", "stopped")
    assert body["version"]
    assert body["uptime_seconds"] >= 0


def test_root_endpoint_lists_urls(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/api/docs"


def test_events_endpoint_and_filters(client, db_ready):
    process_message(CISCO_DOWN, "10.30.0.1")
    process_message(LINUX_AUTH, "10.30.0.2")

    # All events
    response = client.get("/api/v1/events?limit=100")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    assert len(body["items"]) == body["total"] or len(body["items"]) == 100

    # Free-text search
    response = client.get("/api/v1/events", params={"q": "changed state to down"})
    body = response.json()
    assert body["total"] >= 1
    assert all("changed state to down" in item["message"] for item in body["items"])

    # Exact severity (PRI 85 → severity 5)
    response = client.get("/api/v1/events", params={"severity": 5, "q": "Failed password"})
    body = response.json()
    assert body["total"] >= 1
    assert all(item["severity"] == 5 for item in body["items"])

    # Device source IP filter
    response = client.get("/api/v1/events", params={"device_ip": "10.30.0.1"})
    body = response.json()
    assert body["total"] >= 1
    assert all(item["source_ip"] == "10.30.0.1" for item in body["items"])

    # Event type filter
    response = client.get("/api/v1/events", params={"event_type": "AUTH_FAILURE"})
    body = response.json()
    assert body["total"] >= 1
    assert all(item["event_type_code"] == "AUTH_FAILURE" for item in body["items"])

    # Invalid severity → validation error
    assert client.get("/api/v1/events", params={"severity": 42}).status_code == 422


def test_single_event_endpoint(client, db_ready):
    created = process_message(CISCO_DOWN, "10.30.0.5")

    response = client.get(f"/api/v1/events/{created.id}")
    assert response.status_code == 200
    assert response.json()["id"] == created.id

    assert client.get("/api/v1/events/999999999").status_code == 404


def test_devices_endpoint(client, db_ready):
    process_message(CISCO_DOWN, "10.30.0.6")

    response = client.get("/api/v1/devices")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    device = next(d for d in body["items"] if d["ip_address"] == "10.30.0.6")
    assert device["event_count"] >= 1
    assert device["vendor"] == "cisco"


def test_event_types_endpoint(client):
    response = client.get("/api/v1/event-types")
    assert response.status_code == 200
    codes = {item["code"] for item in response.json()}
    assert {"INTERFACE_DOWN", "BGP_DOWN", "AUTH_FAILURE", "OTHER"} <= codes
