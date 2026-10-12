"""Pure unit tests: incident scoring, root-cause ranking, correlation rules."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.correlation.config import CorrelationConfig
from app.correlation.rules import (
    CausalChainRule,
    CrossDeviceSameTypeRule,
    IncidentSnapshot,
    SameCorrelationKeyRule,
    SameDeviceSubsystemRule,
    SharedEndpointRule,
    alert_key,
    match_score,
)
from app.correlation.scoring import compute_incident_score, rank_root_causes


def _alert(event_type="INTERFACE_DOWN", severity="HIGH", device_id=1,
           context=None, event_count=1, when=None):
    when = when or datetime.now(timezone.utc)
    return SimpleNamespace(
        id=1,
        event_type=event_type,
        severity=severity,
        device_id=device_id,
        context=context or {},
        event_count=event_count,
        first_seen_at=when,
        last_seen_at=when,
    )


class TestScoring:
    def test_more_alerts_score_higher(self):
        config = CorrelationConfig()
        now = datetime.now(timezone.utc)
        one = [_alert(severity="HIGH", when=now)]
        many = [
            _alert(severity="HIGH", when=now),
            _alert("ROUTE_CHANGE", "LOW", when=now),
            _alert("DEVICE_UNREACHABLE", "CRITICAL", when=now),
        ]
        assert compute_incident_score(many, "rtr1", config) > (
            compute_incident_score(one, "rtr1", config)
        )

    def test_critical_device_boosts_score(self):
        config = CorrelationConfig()
        alert = _alert()
        core = compute_incident_score([alert], "rtr-core-01", config)
        plain = compute_incident_score([alert], "web01", config)
        assert round(core - plain, 2) == config.score_device_importance_weight

    def test_higher_severity_scores_higher(self):
        config = CorrelationConfig()
        critical = compute_incident_score([_alert(severity="CRITICAL")], "h1", config)
        low = compute_incident_score([_alert(severity="LOW")], "h1", config)
        assert critical > low

    def test_info_severity_maps_to_low(self):
        config = CorrelationConfig()
        info = compute_incident_score(
            [_alert(severity="INFO", event_type="INTERFACE_UP")], "h1", config
        )
        low = compute_incident_score(
            [_alert(severity="LOW", event_type="INTERFACE_UP")], "h1", config
        )
        assert info == low  # INFO counts as LOW on the incident scale


class TestRootCauseRanking:
    def test_interface_failure_with_corroboration_ranks_first(self):
        alerts = [
            _alert("INTERFACE_DOWN", "HIGH"),
            _alert("ROUTE_CHANGE", "LOW"),
            _alert("DEVICE_UNREACHABLE", "CRITICAL"),
        ]
        ranked = rank_root_causes(alerts, "rtr1", CorrelationConfig())
        assert ranked[0]["code"] == "interface_failure"
        assert ranked[0]["confidence"] >= 0.94
        assert ranked[0]["evidence"]  # auditable evidence list

    def test_bgp_route_pair_ranks_bgp_first(self):
        alerts = [_alert("BGP_DOWN", "HIGH"), _alert("ROUTE_CHANGE", "LOW")]
        ranked = rank_root_causes(alerts, "rtr1", CorrelationConfig())
        assert ranked[0]["code"] == "bgp_peer_failure"

    def test_multi_device_ranks_isp_outage_first(self):
        alerts = [
            _alert("BGP_DOWN", "HIGH", device_id=1),
            _alert("BGP_DOWN", "HIGH", device_id=2),
        ]
        ranked = rank_root_causes(alerts, "edge1", CorrelationConfig())
        assert ranked[0]["code"] == "upstream_isp_outage"

    def test_empty_alerts_no_candidates(self):
        assert rank_root_causes([], "h1", CorrelationConfig()) == []


class TestCorrelationRules:
    def test_same_key_rule(self):
        config = CorrelationConfig()
        alert = _alert(context={"interface": "Gi0/1"})
        snapshot = IncidentSnapshot(incident_id=1, correlation_key=alert_key(alert))
        assert SameCorrelationKeyRule().score(alert, snapshot, config) > 0

    def test_causal_chain_rule(self):
        config = CorrelationConfig()
        alert = _alert("ROUTE_CHANGE", "LOW")
        snapshot = IncidentSnapshot(incident_id=1, correlation_key="k")
        snapshot.device_ids.add(1)
        snapshot.event_types.add("INTERFACE_DOWN")
        snapshot.categories.add("interface")
        assert CausalChainRule().score(alert, snapshot, config) > 0

    def test_shared_endpoint_across_devices(self):
        config = CorrelationConfig()
        alert = _alert("BGP_DOWN", "HIGH", device_id=2, context={"neighbor": "10.0.0.1"})
        snapshot = IncidentSnapshot(incident_id=1, correlation_key="endpoint:10.0.0.1")
        snapshot.endpoints.add("10.0.0.1")
        assert SharedEndpointRule().score(alert, snapshot, config) > 0

    def test_cross_device_same_type_alone_below_threshold(self):
        config = CorrelationConfig()
        alert = _alert("BGP_DOWN", "HIGH", device_id=9)
        snapshot = IncidentSnapshot(incident_id=1, correlation_key="k")
        snapshot.event_types.add("BGP_DOWN")
        score = CrossDeviceSameTypeRule().score(alert, snapshot, config)
        assert 0 < score < config.min_match_score

    def test_subsystem_rule_and_no_match(self):
        config = CorrelationConfig()
        alert = _alert("CPU_HIGH", "MEDIUM", device_id=7)
        snapshot = IncidentSnapshot(incident_id=1, correlation_key="other")
        snapshot.device_ids.add(7)
        snapshot.categories.add("performance")
        assert SameDeviceSubsystemRule().score(alert, snapshot, config) > 0
        other = IncidentSnapshot(incident_id=2, correlation_key="x")
        assert match_score(alert, other, [SameDeviceSubsystemRule()], config) == 0.0

