"""Incident API tests: list/filter, detail, lifecycle actions, timeline, WS."""

from sqlalchemy import select

from app.correlation.engine import get_correlation_engine
from app.db.session import SessionLocal
from app.models.models import Incident
from app.realtime.broadcaster import alert_broadcaster
from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 api-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/6, changed state to down"
)


def _first_incident_id():
    with SessionLocal() as db:
        incident = db.execute(select(Incident)).scalars().first()
        assert incident is not None
        return incident.id


def test_incidents_list_and_filters(client, db_ready):
    process_message(CISCO_DOWN, "10.43.0.1")

    body = client.get("/api/v1/incidents").json()
    assert body["total"] == 1
    incident = body["items"][0]
    assert incident["status"] == "OPEN"
    assert incident["severity"] == "HIGH"
    assert incident["score"] > 0

    assert client.get("/api/v1/incidents", params={"status": "OPEN"}).json()["total"] == 1
    assert (
        client.get("/api/v1/incidents", params={"status": "CLOSED"}).json()["total"] == 0
    )
    assert (
        client.get("/api/v1/incidents", params={"severity": "HIGH"}).json()["total"] == 1
    )
    assert (
        client.get("/api/v1/incidents", params={"category": "interface"}).json()["total"]
        == 1
    )
    assert (
        client.get("/api/v1/incidents", params={"q": "GigabitEthernet"}).json()["total"]
        == 1
    )
    assert (
        client.get("/api/v1/incidents", params={"min_score": 1.0}).json()["total"] == 1
    )
    assert (
        client.get("/api/v1/incidents", params={"min_score": 10000.0}).json()["total"]
        == 0
    )
    assert client.get("/api/v1/incidents", params={"status": "banana"}).status_code == 422


def test_incident_detail_includes_alerts(client, db_ready):
    process_message(CISCO_DOWN, "10.43.0.2")
    incident_id = _first_incident_id()

    response = client.get(f"/api/v1/incidents/{incident_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["incident"]["id"] == incident_id
    assert body["incident"]["root_cause_candidates"]
    assert len(body["alerts"]) == 1
    assert body["alerts"][0]["event_type"] == "INTERFACE_DOWN"

    assert client.get("/api/v1/incidents/999999999").status_code == 404


def test_acknowledge_resolve_close_flow(client, db_ready):
    process_message(CISCO_DOWN, "10.43.0.3")
    incident_id = _first_incident_id()

    # close is only allowed from RESOLVED
    assert client.post(f"/api/v1/incidents/{incident_id}/close").status_code == 409

    acked = client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge", json={"actor": "carol"}
    )
    assert acked.status_code == 200
    assert acked.json()["status"] == "ACKNOWLEDGED"
    assert acked.json()["acknowledged_by"] == "carol"

    # acknowledge is idempotent while ACKNOWLEDGED
    again = client.post(f"/api/v1/incidents/{incident_id}/acknowledge")
    assert again.status_code == 200
    assert again.json()["status"] == "ACKNOWLEDGED"

    resolved = client.post(f"/api/v1/incidents/{incident_id}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_at"] is not None

    assert client.post(f"/api/v1/incidents/{incident_id}/resolve").status_code == 409
    assert (
        client.post(f"/api/v1/incidents/{incident_id}/acknowledge").status_code == 409
    )

    closed = client.post(
        f"/api/v1/incidents/{incident_id}/close", json={"actor": "carol"}
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert client.post(f"/api/v1/incidents/{incident_id}/close").status_code == 409

    assert client.post("/api/v1/incidents/999999999/resolve").status_code == 404


def test_timeline_endpoint(client, db_ready):
    process_message(CISCO_DOWN, "10.43.0.4")
    incident_id = _first_incident_id()
    client.post(f"/api/v1/incidents/{incident_id}/acknowledge", json={"actor": "dave"})

    response = client.get(f"/api/v1/incidents/{incident_id}/timeline")
    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == incident_id
    types = {entry["type"] for entry in body["entries"]}
    assert {"state_change", "alert", "event"} <= types
    assert client.get("/api/v1/incidents/999999999/timeline").status_code == 404


def test_websocket_streams_incident_frames(client, db_ready):
    assert alert_broadcaster._loop is not None

    with client.websocket_connect("/api/v1/ws/alerts") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "connected"

        process_message(CISCO_DOWN, "10.43.0.5")  # alert payload + incident payload

        frames = [ws.receive_json(), ws.receive_json()]
        types_seen = {frame["type"] for frame in frames}
        assert "alert" in types_seen and "incident" in types_seen
        incident_frame = next(f for f in frames if f["type"] == "incident")
        assert incident_frame["action"] == "created"
        assert incident_frame["incident"]["status"] == "OPEN"
        assert incident_frame["incident"]["severity"] == "HIGH"
