"""Phase 4 tests: topology graph, highlighting, device/link CRUD."""

from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 topo-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/5, changed state to down"
)


def _device_payload(ip, hostname="topo-node", device_type="router", **extra):
    payload = {
        "hostname": hostname,
        "ip_address": ip,
        "device_type": device_type,
    }
    payload.update(extra)
    return payload


def _link_payload(client, ip_a="10.50.0.1", ip_b="10.50.0.2", **extra):
    a = client.post("/api/v1/devices", json=_device_payload(ip_a, "topo-a")).json()
    b = client.post(
        "/api/v1/devices", json=_device_payload(ip_b, "topo-b", "switch")
    ).json()
    payload = {
        "source_device_id": a["id"],
        "source_interface": "Gi0/1",
        "target_device_id": b["id"],
        "target_interface": "Gi0/2",
    }
    payload.update(extra)
    return a, b, payload


class TestTopologyGraph:
    def test_graph_returns_nodes_and_links(self, client, db_ready):
        a, b, payload = _link_payload(client)
        created = client.post("/api/v1/links", json=payload)
        assert created.status_code == 201

        graph = client.get("/api/v1/topology").json()
        node_ids = {node["id"] for node in graph["nodes"]}
        assert {a["id"], b["id"]} <= node_ids
        link = graph["links"][0]
        assert link["source_device_id"] == a["id"]
        assert link["target_device_id"] == b["id"]
        assert link["status"] == "up"
        assert link["affected"] is False
        types = {node["id"]: node["device_type"] for node in graph["nodes"]}
        assert types[a["id"]] == "router"
        assert types[b["id"]] == "switch"

    def test_open_alert_marks_node_and_link_affected(self, client, db_ready):
        process_message(CISCO_DOWN, "10.50.1.1")
        devices = client.get("/api/v1/devices").json()
        node = next(d for d in devices["items"] if d["ip_address"] == "10.50.1.1")
        peer = client.post(
            "/api/v1/devices", json=_device_payload("10.50.1.2", "peer1")
        ).json()
        client.post(
            "/api/v1/links",
            json={
                "source_device_id": node["id"],
                "source_interface": "GigabitEthernet0/5",
                "target_device_id": peer["id"],
                "target_interface": "eth0",
            },
        )

        graph = client.get("/api/v1/topology").json()
        affected_node = next(n for n in graph["nodes"] if n["id"] == node["id"])
        assert affected_node["affected"] is True
        assert affected_node["max_severity"] == "HIGH"
        assert affected_node["open_alert_count"] >= 1
        affected_link = next(
            link for link in graph["links"] if link["source_device_id"] == node["id"]
        )
        assert affected_link["affected"] is True
        assert affected_link["max_severity"] == "HIGH"

    def test_resolving_alert_clears_highlighting(self, client, db_ready):
        process_message(CISCO_DOWN, "10.50.2.1")
        alerts = client.get("/api/v1/alerts").json()
        assert alerts["total"] >= 1
        client.post(f"/api/v1/alerts/{alerts['items'][0]['id']}/resolve")
        # The correlated incident is still OPEN — it also drives highlighting,
        # so resolve it too to reach a fully clean state.
        for incident in client.get("/api/v1/incidents").json()["items"]:
            client.post(f"/api/v1/incidents/{incident['id']}/resolve")

        graph = client.get("/api/v1/topology").json()
        node = next(
            n for n in graph["nodes"] if n["id"] == alerts["items"][0]["device_id"]
        )
        assert node["affected"] is False
        assert node["max_severity"] is None


class TestDeviceCrud:
    def test_create_and_read_device(self, client, db_ready):
        response = client.post(
            "/api/v1/devices", json=_device_payload("10.50.3.1", "fw1", "firewall")
        )
        assert response.status_code == 201
        body = response.json()
        assert body["device_type"] == "firewall"
        assert body["status"] == "active"

    def test_all_node_types_supported(self, client, db_ready):
        for index, device_type in enumerate(["router", "switch", "firewall", "server"]):
            response = client.post(
                "/api/v1/devices",
                json=_device_payload(f"10.50.4.{index + 1}", f"n{index}", device_type),
            )
            assert response.status_code == 201
            assert response.json()["device_type"] == device_type

    def test_validation_rejects_bad_input(self, client, db_ready):
        bad_type = dict(_device_payload("10.50.5.1"), device_type="toaster")
        assert client.post("/api/v1/devices", json=bad_type).status_code == 422
        bad_ip = dict(_device_payload("not-an-ip"))
        assert client.post("/api/v1/devices", json=bad_ip).status_code == 422
        assert (
            client.post("/api/v1/devices", json={"ip_address": "10.50.5.2"}).status_code
            == 422
        )

    def test_duplicate_ip_conflict(self, client, db_ready):
        assert (
            client.post("/api/v1/devices", json=_device_payload("10.50.6.1")).status_code
            == 201
        )
        assert (
            client.post("/api/v1/devices", json=_device_payload("10.50.6.1")).status_code
            == 409
        )

    def test_edit_device(self, client, db_ready):
        created = client.post(
            "/api/v1/devices", json=_device_payload("10.50.7.1", "edit-me")
        ).json()
        updated = client.patch(
            f"/api/v1/devices/{created['id']}",
            json={"device_type": "server", "status": "maintenance", "hostname": "edited"},
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["device_type"] == "server"
        assert body["status"] == "maintenance"
        assert body["hostname"] == "edited"
        assert (
            client.patch("/api/v1/devices/999999999", json={"status": "offline"}).status_code
            == 404
        )

    def test_delete_device_cleans_links(self, client, db_ready):
        a, b, payload = _link_payload(client, ip_a="10.50.8.1", ip_b="10.50.8.2")
        client.post("/api/v1/links", json=payload)

        assert client.delete(f"/api/v1/devices/{a['id']}").status_code == 204
        graph = client.get("/api/v1/topology").json()
        assert a["id"] not in {node["id"] for node in graph["nodes"]}
        assert graph["links"] == []  # link removed with the device
        assert client.delete(f"/api/v1/devices/{a['id']}").status_code == 404


class TestLinkCrud:
    def test_create_link(self, client, db_ready):
        _a, _b, payload = _link_payload(client, ip_a="10.50.9.1", ip_b="10.50.9.2")
        response = client.post("/api/v1/links", json=payload)
        assert response.status_code == 201
        assert response.json()["status"] == "up"

    def test_link_validation(self, client, db_ready):
        a, b, payload = _link_payload(client, ip_a="10.50.10.1", ip_b="10.50.10.2")

        # self-link rejected
        self_link = dict(payload, target_device_id=a["id"], target_interface="x")
        assert client.post("/api/v1/links", json=self_link).status_code == 422
        # missing device rejected
        missing = dict(payload, target_device_id=999999999)
        assert client.post("/api/v1/links", json=missing).status_code == 404
        # empty interface rejected by schema
        empty = dict(payload, source_interface="")
        assert client.post("/api/v1/links", json=empty).status_code == 422
        # duplicate rejected
        assert client.post("/api/v1/links", json=payload).status_code == 201
        assert client.post("/api/v1/links", json=payload).status_code == 409

    def test_edit_and_delete_link(self, client, db_ready):
        _a, _b, payload = _link_payload(client, ip_a="10.50.11.1", ip_b="10.50.11.2")
        link = client.post("/api/v1/links", json=payload).json()

        updated = client.patch(
            f"/api/v1/links/{link['id']}", json={"status": "down"}
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "down"

        assert client.delete(f"/api/v1/links/{link['id']}").status_code == 204
        assert client.delete(f"/api/v1/links/{link['id']}").status_code == 404
        assert client.patch("/api/v1/links/999999999", json={"status": "up"}).status_code == 404
