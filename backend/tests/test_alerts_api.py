"""API tests: alert listing/filtering, detail, acknowledge/resolve, WebSocket."""

from app.realtime.broadcaster import alert_broadcaster
from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 api-alert-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/5, changed state to down"
)
CISCO_UP = (
    b"<134>Jan 15 10:24:00 api-alert-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/5, changed state to up"
)


def _first_alert_id(client, **params):
    body = client.get("/api/v1/alerts", params=params).json()
    assert body["total"] >= 1
    return body["items"][0]["id"]


def test_alerts_list_and_filters(client, db_ready):
    process_message(CISCO_DOWN, "10.37.0.1")
    process_message(CISCO_UP, "10.37.0.2")

    body = client.get("/api/v1/alerts").json()
    assert body["total"] == 2
    assert {item["event_type"] for item in body["items"]} == {
        "INTERFACE_DOWN",
        "INTERFACE_UP",
    }

    high = client.get("/api/v1/alerts", params={"severity": "HIGH"}).json()
    assert high["total"] >= 1
    assert all(item["severity"] == "HIGH" for item in high["items"])

    down = client.get(
        "/api/v1/alerts", params={"event_type": "INTERFACE_DOWN"}
    ).json()
    assert down["total"] == 1

    new = client.get("/api/v1/alerts", params={"status": "new"}).json()
    assert all(item["status"] == "new" for item in new["items"])

    search = client.get(
        "/api/v1/alerts", params={"q": "GigabitEthernet0/5"}
    ).json()
    assert search["total"] == 2

    device_id = body["items"][0]["device_id"]
    by_device = client.get(
        "/api/v1/alerts", params={"device_id": device_id}
    ).json()
    assert by_device["total"] >= 1

    # pagination
    page = client.get("/api/v1/alerts", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1


def test_invalid_alert_filters_rejected(client):
    assert client.get("/api/v1/alerts", params={"severity": "ULTRA"}).status_code == 422
    assert client.get("/api/v1/alerts", params={"status": "banana"}).status_code == 422


def test_alert_detail_includes_device_and_event(client, db_ready):
    process_message(CISCO_DOWN, "10.37.0.3")
    alert_id = _first_alert_id(client, event_type="INTERFACE_DOWN")

    response = client.get(f"/api/v1/alerts/{alert_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["alert"]["id"] == alert_id
    assert body["alert"]["rule_name"] == "interface_state"
    assert body["device"]["ip_address"] == "10.37.0.3"
    assert body["event"]["message"].startswith("%LINK-3-UPDOWN")
    assert body["event"]["event_type_code"] == "INTERFACE_DOWN"

    assert client.get("/api/v1/alerts/999999999").status_code == 404


def test_acknowledge_and_resolve_flow(client, db_ready):
    process_message(CISCO_DOWN, "10.37.0.4")
    alert_id = _first_alert_id(client, event_type="INTERFACE_DOWN")

    acked = client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge", json={"actor": "alice"}
    )
    assert acked.status_code == 200
    assert acked.json()["status"] == "acknowledged"
    assert acked.json()["acknowledged_by"] == "alice"
    assert acked.json()["acknowledged_at"] is not None

    resolved = client.post(
        f"/api/v1/alerts/{alert_id}/resolve", json={"actor": "alice"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None

    # Terminal state: no double-resolve, no ack after resolve.
    assert (
        client.post(f"/api/v1/alerts/{alert_id}/resolve").status_code == 409
    )
    assert (
        client.post(f"/api/v1/alerts/{alert_id}/acknowledge").status_code == 409
    )
    assert client.post("/api/v1/alerts/999999999/resolve").status_code == 404


def test_resolve_from_new_allowed_without_prior_ack(client, db_ready):
    process_message(CISCO_DOWN, "10.37.0.5")
    alert_id = _first_alert_id(client, event_type="INTERFACE_DOWN")

    resolved = client.post(f"/api/v1/alerts/{alert_id}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["acknowledged_by"] == "api-user"  # backfilled


def test_health_includes_detection_check(client):
    from app.detection.rules import DEFAULT_RULES

    body = client.get("/api/v1/health").json()
    detection = body["checks"]["detection"]
    assert detection["status"] in ("ok", "disabled")
    assert detection["rules"] == len(DEFAULT_RULES)
    assert "alerts_created" in detection
    assert "websocket_subscribers" in detection
    assert "correlation" in body["checks"]


def test_websocket_streams_created_alerts(client, db_ready):
    assert alert_broadcaster._loop is not None  # bound by the lifespan

    with client.websocket_connect("/api/v1/ws/alerts") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "connected"

        process_message(CISCO_DOWN, "10.37.0.6")  # raises INTERFACE_DOWN

        frame = ws.receive_json()
        assert frame["type"] == "alert"
        assert frame["action"] == "created"
        assert frame["alert"]["event_type"] == "INTERFACE_DOWN"
        assert frame["alert"]["severity"] == "HIGH"
        assert frame["alert"]["hostname"] == "api-alert-rtr"
