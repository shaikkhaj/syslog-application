"""Phase 5 tests: RCA device ranking, health-score calculation, API responses."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.health.rca import (
    DeviceEvidence,
    build_adjacency,
    rank_devices,
    tier_of,
    upstream_dependencies,
)
from app.health.scoring import (
    DeviceSignals,
    HealthConfig,
    band_for,
    compute_device_health,
    compute_overall_health,
)
from app.syslog.pipeline import process_message

CISCO_DOWN = (
    b"<134>Jan 15 10:23:45 ph5-rtr: %LINK-3-UPDOWN: Interface "
    b"GigabitEthernet0/5, changed state to down"
)

BASE = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


def _link(source: int, target: int) -> SimpleNamespace:
    return SimpleNamespace(source_device_id=source, target_device_id=target)


def _evidence(device_id: int, *, severity="HIGH", event_type="INTERFACE_DOWN",
              first_seen=None, primary=False, critical=False) -> DeviceEvidence:
    return DeviceEvidence(
        device_id=device_id,
        severities=[severity],
        event_types=[event_type],
        first_seen=first_seen,
        is_incident_primary=primary,
        is_critical=critical,
    )


class TestHealthScoring:
    def test_clean_device_scores_full(self):
        health = compute_device_health(DeviceSignals(device_id=1))
        assert health["score"] == 100.0
        assert health["band"] == "healthy"
        assert all(value == 0 for value in health["breakdown"].values())

    def test_critical_alert_penalises_and_caps(self):
        config = HealthConfig()
        one = compute_device_health(
            DeviceSignals(device_id=1, alert_severities=["CRITICAL"]), config
        )
        assert one["breakdown"]["alerts"] == 35.0
        assert one["score"] == 65.0 and one["band"] == "degraded"
        many = compute_device_health(
            DeviceSignals(device_id=1, alert_severities=["CRITICAL"] * 5), config
        )
        assert many["breakdown"]["alerts"] == config.alert_penalty_cap
        assert many["score"] == 40.0 and many["band"] == "critical"

    def test_active_incident_penalty_by_severity(self):
        health = compute_device_health(
            DeviceSignals(device_id=1, incident_severities=["CRITICAL", "LOW"])
        )
        assert health["breakdown"]["incidents"] == 34.0
        assert health["score"] == 66.0
        # resolved/closed incidents never reach the aggregator (query filters),
        # so an empty list must stay penalty-free:
        assert compute_device_health(DeviceSignals(device_id=1))["score"] == 100.0

    def test_event_frequency_penalty_only_above_baseline(self):
        config = HealthConfig()
        quiet = compute_device_health(
            DeviceSignals(device_id=1, recent_event_count=config.event_baseline), config
        )
        assert quiet["breakdown"]["events"] == 0.0
        busy = compute_device_health(
            DeviceSignals(device_id=1, recent_event_count=config.event_baseline + 20),
            config,
        )
        assert busy["breakdown"]["events"] == 10.0
        flood = compute_device_health(
            DeviceSignals(device_id=1, recent_event_count=10_000), config
        )
        assert flood["breakdown"]["events"] == config.event_penalty_cap

    def test_status_penalties_and_floor(self):
        offline = compute_device_health(DeviceSignals(device_id=1, status="offline"))
        assert offline["breakdown"]["status"] == 25.0
        assert offline["score"] == 75.0
        maintenance = compute_device_health(
            DeviceSignals(device_id=1, status="maintenance")
        )
        assert maintenance["breakdown"]["status"] == 10.0
        worst = compute_device_health(
            DeviceSignals(
                device_id=1,
                status="offline",
                alert_severities=["CRITICAL"] * 5,
                incident_severities=["CRITICAL"] * 5,
                recent_event_count=10_000,
            )
        )
        assert worst["score"] == 0.0 and worst["band"] == "critical"

    def test_band_thresholds(self):
        assert band_for(80.0) == "healthy"
        assert band_for(79.9) == "degraded"
        assert band_for(50.0) == "degraded"
        assert band_for(49.9) == "critical"

    def test_overall_health_is_mean_with_counts(self):
        overall = compute_overall_health([100.0, 80.0, 60.0])
        assert overall["score"] == 80.0
        assert overall["band"] == "healthy"
        assert overall["counts"] == {"healthy": 2, "degraded": 1, "critical": 0}

    def test_overall_health_empty_network_is_healthy(self):
        overall = compute_overall_health([])
        assert overall["score"] == 100.0
        assert overall["band"] == "healthy"


class TestRcaRanking:
    def test_tier_model_and_adjacency(self):
        assert tier_of("firewall") < tier_of("router") < tier_of("switch")
        assert tier_of(None) == tier_of("weird") == 1
        adjacency = build_adjacency([_link(1, 2), _link(2, 3), _link(4, 4)])
        assert adjacency == {1: {2}, 2: {1, 3}, 3: {2}}  # self loop dropped

    def test_empty_evidence_returns_empty(self):
        assert rank_devices({}) == []

    def test_earliest_alert_device_ranks_first(self):
        evidence = {
            1: _evidence(1, first_seen=BASE + timedelta(seconds=45)),
            2: _evidence(2, first_seen=BASE),
        }
        ranking = rank_devices(evidence)
        assert [entry["device_id"] for entry in ranking] == [2, 1]
        assert ranking[0]["rank"] == 1
        assert any("first alert" in reason for reason in ranking[0]["reasons"])
        # earliest (+6) separates identical severity evidence
        assert ranking[0]["score"] - ranking[1]["score"] == 6.0

    def test_upstream_router_outranks_downstream_switch(self):
        evidence = {1: _evidence(1), 2: _evidence(2)}  # identical evidence
        adjacency = build_adjacency([_link(1, 2)])
        tiers = {1: tier_of("router"), 2: tier_of("switch")}
        ranking = rank_devices(evidence, adjacency, tiers, labels={1: "core", 2: "access"})
        assert ranking[0]["device_id"] == 1  # router is upstream of switch
        assert any("upstream of alerting access" in r for r in ranking[0]["reasons"])
        assert not any(
            "upstream" in r and "core" not in r for r in ranking[1]["reasons"]
        )

    def test_severity_and_primary_device_bonuses(self):
        evidence = {
            1: _evidence(1, severity="CRITICAL", primary=True),
            2: _evidence(2, severity="LOW"),
        }
        ranking = rank_devices(evidence)
        top = ranking[0]
        # 10 severity + 4 failure + 6 earliest(if first) + 2 primary
        assert top["device_id"] == 1
        assert any("incident primary device" in r for r in top["reasons"])
        assert any("max severity CRITICAL" in r for r in top["reasons"])

    def test_consequence_only_evidence_scores_lower(self):
        failure = {1: _evidence(1, event_type="INTERFACE_DOWN")}
        consequence = {2: _evidence(2, event_type="ROUTE_CHANGE")}
        assert rank_devices(failure)[0]["score"] > rank_devices(consequence)[0]["score"]

    def test_upstream_dependencies_walk_toward_core(self):
        # 1 firewall — 2 router — 3 switch — 4 server
        adjacency = build_adjacency([_link(1, 2), _link(2, 3), _link(3, 4)])
        tiers = {1: 0, 2: 1, 3: 2, 4: 3}
        deps = upstream_dependencies(3, adjacency, tiers, labels={3: "access"})
        assert [entry["device_id"] for entry in deps] == [2, 1]
        assert [entry["hops"] for entry in deps] == [1, 2]
        assert all("upstream of access" in entry["reason"] for entry in deps)
        # downstream server is never a dependency
        assert 4 not in {entry["device_id"] for entry in deps}
        # a firewall primary has nothing strictly upstream
        assert upstream_dependencies(1, adjacency, tiers) == []
        # max_hops truncates the walk
        capped = upstream_dependencies(3, adjacency, tiers, max_hops=1)
        assert [entry["device_id"] for entry in capped] == [2]


def _device(client, ip, hostname, device_type="router"):
    return client.post(
        "/api/v1/devices",
        json={
            "hostname": hostname,
            "ip_address": ip,
            "device_type": device_type,
        },
    ).json()


class TestRcaApi:
    def test_unknown_incident_returns_404(self, client, db_ready):
        assert client.get("/api/v1/incidents/999999999/rca").status_code == 404

    @staticmethod
    def _device_by_ip(client, ip):
        devices = client.get("/api/v1/devices", params={"limit": 500}).json()["items"]
        return next(device for device in devices if device["ip_address"] == ip)

    @staticmethod
    def _incident_for(client, device_id):
        incidents = client.get("/api/v1/incidents").json()["items"]
        return next(i for i in incidents if i["device_id"] == device_id)

    def test_rca_report_ranks_devices_and_upstream(self, client, db_ready):
        process_message(CISCO_DOWN, "10.55.0.1")  # raises INTERFACE_DOWN alert
        router = self._device_by_ip(client, "10.55.0.1")
        # topology: firewall (core) upstream of the alerting router
        firewall = _device(client, "10.55.0.254", "ph5-fw", "firewall")
        client.post(
            "/api/v1/links",
            json={
                "source_device_id": firewall["id"],
                "source_interface": "Gi0/0",
                "target_device_id": router["id"],
                "target_interface": "Gi0/1",
            },
        )
        incident = self._incident_for(client, router["id"])

        response = client.get(f"/api/v1/incidents/{incident['id']}/rca")
        assert response.status_code == 200
        body = response.json()
        assert body["incident_id"] == incident["id"]
        assert body["primary_device_id"] == router["id"]
        # Phase 3 candidates are reused, not re-derived
        assert body["candidates"][0]["code"] == "interface_failure"
        assert body["confidence"] is not None and body["confidence"] > 0
        assert "Probable root cause" in body["summary"]
        # device ranking: alerting router first, with audit reasons
        top = body["device_ranking"][0]
        assert top["device_id"] == router["id"]
        assert top["rank"] == 1
        assert top["reasons"] and any("member alert" in r for r in top["reasons"])
        # upstream dependency: the firewall is 1 hop above the suspect
        upstream_ids = [u["device_id"] for u in body["upstream_dependencies"]]
        assert firewall["id"] in upstream_ids
        hop1 = next(
            u for u in body["upstream_dependencies"] if u["device_id"] == firewall["id"]
        )
        assert hop1["hops"] == 1
        assert "upstream" in hop1["reason"]
        assert hop1["device_type"] == "firewall"

    def test_rca_report_without_topology_has_no_upstream(self, client, db_ready):
        process_message(CISCO_DOWN, "10.55.1.1")
        device = self._device_by_ip(client, "10.55.1.1")
        incident = self._incident_for(client, device["id"])
        body = client.get(f"/api/v1/incidents/{incident['id']}/rca").json()
        assert body["device_ranking"]
        assert body["primary_device_id"] == device["id"]
        assert body["upstream_dependencies"] == []


class TestNetworkHealthApi:
    def test_endpoint_shape_and_counts(self, client, db_ready):
        body = client.get("/api/v1/network-health").json()
        assert body["window_minutes"] == 60
        assert body["device_count"] > 0
        assert set(body["counts"]) == {"healthy", "degraded", "critical"}
        assert sum(body["counts"].values()) == body["device_count"]
        assert body["band"] in ("healthy", "degraded", "critical")
        assert 0 <= body["overall_score"] <= 100
        # worst first
        scores = [item["score"] for item in body["items"]]
        assert scores == sorted(scores)

    def test_clean_device_is_healthy_at_full_score(self, client, db_ready):
        device = _device(client, "10.56.0.1", "ph5-clean")
        body = client.get("/api/v1/network-health", params={"device_id": device["id"]}).json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["score"] == 100.0
        assert item["band"] == "healthy"
        assert item["open_alerts"] == 0 and item["active_incidents"] == 0
        assert item["breakdown"] == {
            "alerts": 0,
            "incidents": 0,
            "events": 0,
            "status": 0,
        }

    def test_alerting_device_drops_below_full_score(self, client, db_ready):
        process_message(CISCO_DOWN, "10.56.1.1")  # HIGH alert + OPEN incident
        device = next(
            item
            for item in client.get("/api/v1/devices", params={"limit": 500}).json()["items"]
            if item["ip_address"] == "10.56.1.1"
        )
        body = client.get("/api/v1/network-health", params={"device_id": device["id"]}).json()
        item = body["items"][0]
        assert item["score"] < 100.0
        assert item["band"] in ("degraded", "critical")
        assert item["open_alerts"] >= 1
        assert item["active_incidents"] >= 1
        assert item["max_alert_severity"] in ("HIGH", "CRITICAL")
        assert item["recent_events"] >= 1
        assert item["breakdown"]["alerts"] > 0
        assert item["breakdown"]["incidents"] > 0
        assert item["breakdown"]["events"] >= 0
