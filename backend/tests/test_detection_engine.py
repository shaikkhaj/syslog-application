"""Engine-level tests: registry, taxonomy, dedupe, stats, error isolation."""

from app.db.session import SessionLocal
from app.detection.alert_service import raise_alert
from app.detection.config import DetectionConfig
from app.detection.engine import DetectionEngine
from app.detection.rules import DEFAULT_RULES, DetectionRule
from app.detection.types import AlertSeverity, AlertStatus, DetectionResult, EventType
from app.models.models import Alert

REQUIRED_TYPES = {
    "INTERFACE_DOWN",
    "INTERFACE_UP",
    "LINK_FLAP",
    "BGP_DOWN",
    "BGP_UP",
    "OSPF_NEIGHBOR_DOWN",
    "AUTH_FAILURE",
    "CONFIG_CHANGE",
    "CPU_HIGH",
    "MEMORY_HIGH",
    "ROUTE_CHANGE",
    "DEVICE_UNREACHABLE",
}
SEVERITY_SCALE = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_required_classification_types_exist():
    assert REQUIRED_TYPES <= set(EventType.codes())


def test_severity_scale_is_ordered():
    orders = [AlertSeverity.order(severity) for severity in SEVERITY_SCALE]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(SEVERITY_SCALE)


def test_default_rule_registry():
    names = {rule.name for rule in DEFAULT_RULES}
    assert len(DEFAULT_RULES) == 9
    assert {
        "interface_state",
        "link_flap",
        "bgp_state",
        "ospf_state",
        "route_change",
        "auth_failure_threshold",
        "performance_threshold",
        "config_change",
        "device_unreachable",
    } <= names


def test_failing_rule_is_isolated(db_ready, event_factory):
    class FailingRule(DetectionRule):
        name = "failing"

        def evaluate(self, event, db, config):
            raise RuntimeError("boom")

    engine = DetectionEngine(rules=[FailingRule()], config=DetectionConfig())
    event = event_factory(
        "10.36.0.1", "some message", event_type="INTERFACE_DOWN", vendor="cisco"
    )
    with SessionLocal() as db:
        payloads = engine.process(event, db)

    assert payloads == []  # engine did not raise
    assert engine.stats.events_processed == 1
    assert engine.stats.rule_errors == 1


def test_disabled_engine_skips_processing(db_ready, event_factory):
    engine = DetectionEngine(config=DetectionConfig(enabled=False))
    event = event_factory(
        "10.36.0.2", "some message", event_type="INTERFACE_DOWN", vendor="cisco"
    )
    with SessionLocal() as db:
        assert engine.process(event, db) == []
    assert engine.stats.events_processed == 0


def test_engine_creates_alert_with_default_rules(db_ready, event_factory):
    engine = DetectionEngine(config=DetectionConfig())
    event = event_factory(
        "10.36.0.3",
        "Interface Port1 is down",
        event_type="INTERFACE_DOWN",
        interface="Port1",
        vendor="fortinet",
    )
    with SessionLocal() as db:
        payloads = engine.process(event, db)

    assert len(payloads) == 1
    assert payloads[0]["action"] == "created"
    assert payloads[0]["alert"]["event_type"] == "INTERFACE_DOWN"
    assert engine.stats.alerts_created == 1
    assert engine.stats.alerts_updated == 0


def test_dedupe_escalation_and_fresh_alert_after_resolution(
    db_ready, event_factory
):
    event = event_factory("10.36.0.4", "cpu 95%", event_type="CPU_HIGH")
    first = DetectionResult(
        event_type=EventType.CPU_HIGH,
        severity=AlertSeverity.MEDIUM,
        title="High cpu",
        dedupe_key="TEST_DEDUPE:1",
        rule_name="test_rule",
    )
    escalated = DetectionResult(
        event_type=EventType.CPU_HIGH,
        severity=AlertSeverity.CRITICAL,
        title="High cpu",
        dedupe_key="TEST_DEDUPE:1",
        rule_name="test_rule",
    )

    with SessionLocal() as db:
        alert1, created1 = raise_alert(db, first, event)
        db.commit()
        alert2, created2 = raise_alert(db, escalated, event)
        db.commit()
        alert1_id = alert1.id
        alert2_id = alert2.id
        severity = alert2.severity
        count = alert2.event_count

    assert created1 is True
    assert created2 is False  # coalesced
    assert alert1_id == alert2_id
    assert severity == AlertSeverity.CRITICAL.value  # escalated
    assert count == 2

    # Resolving opens the dedupe key for a fresh alert.
    with SessionLocal() as db:
        alert = db.get(Alert, alert1_id)
        alert.status = AlertStatus.RESOLVED.value
        db.commit()
        alert3, created3 = raise_alert(db, first, event)
        db.commit()
        assert created3 is True
        assert alert3.id != alert1_id


def test_stats_snapshot_shape(db_ready):
    engine = DetectionEngine()
    snapshot = engine.snapshot()
    for key in (
        "alerts_created",
        "alerts_updated",
        "rule_errors",
        "events_processed",
        "last_alert_at",
    ):
        assert key in snapshot
