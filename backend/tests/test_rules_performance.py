"""Detection tests: CPU_HIGH / MEMORY_HIGH threshold rule."""

from app.detection.config import DetectionConfig
from app.detection.rules.performance_rules import PerformanceRule
from app.detection.types import AlertSeverity
from app.db.session import SessionLocal
from app.syslog.pipeline import process_message

CPU_93 = (
    b"<133>Jan 15 10:23:45 perf-sw: %CPU_FALLBACK-3-HIGH_CPU: "
    b"cpu_utilization=93% threshold=80% interval=60s"
)
CPU_85_BELOW_DEFAULT = (
    b"<133>Jan 15 10:23:46 perf-sw: %CPU_FALLBACK-3-HIGH_CPU: "
    b"cpu_utilization=85% threshold=80% interval=60s"
)
CPU_UNKNOWN = (
    b"<133>Jan 15 10:23:47 perf-sw: high cpu reported by agent probe"
)
MEMORY_92 = (
    b"<184>date=2026-01-15 time=10:23:45 devname=\"FGT-PERF-01\" "
    b"type=\"system\" subtype=\"memory\" level=\"error\" msg=\"memory_usage=92% "
    b"threshold=90% high memory utilization\""
)


def test_cpu_above_default_threshold_alerts(db_ready, alerts_table):
    process_message(CPU_93, "10.34.0.1")

    alerts = alerts_table.by_type("CPU_HIGH")
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == AlertSeverity.MEDIUM.value
    assert alert.context["utilization_percent"] == 93
    assert alert.context["threshold_percent"] == 90
    assert "93%" in alert.title


def test_cpu_below_default_threshold_suppressed(db_ready, alerts_table):
    # Classified as CPU_HIGH (>=80%) but under the configured 90% threshold.
    process_message(CPU_85_BELOW_DEFAULT, "10.34.0.2")

    assert alerts_table.by_type("CPU_HIGH") == []


def test_cpu_without_percentage_still_alerts(db_ready, alerts_table):
    process_message(CPU_UNKNOWN, "10.34.0.3")

    alerts = alerts_table.by_type("CPU_HIGH")
    assert len(alerts) == 1
    assert alerts[0].context["utilization_percent"] is None


def test_memory_high_alert(db_ready, alerts_table):
    process_message(MEMORY_92, "10.34.0.4")

    alerts = alerts_table.by_type("MEMORY_HIGH")
    assert len(alerts) == 1
    assert alerts[0].severity == AlertSeverity.MEDIUM.value
    assert alerts[0].context["utilization_percent"] == 92
    assert alerts[0].context["threshold_percent"] == 90


def test_configurable_thresholds_suppress_alerts(db_ready, event_factory):
    event = event_factory(
        "10.34.0.5",
        "cpu_utilization=93% threshold=80% interval=60s",
        event_type="CPU_HIGH",
        vendor="cisco",
    )
    strict = DetectionConfig(
        cpu_high_threshold_percent=99, memory_high_threshold_percent=99
    )
    with SessionLocal() as db:
        assert list(PerformanceRule().evaluate(event, db, strict)) == []

    lenient = DetectionConfig(
        cpu_high_threshold_percent=90, memory_high_threshold_percent=90
    )
    with SessionLocal() as db:
        results = list(PerformanceRule().evaluate(event, db, lenient))
    assert len(results) == 1
    assert results[0].context["threshold_percent"] == 90


def test_repeated_high_cpu_coalesces(db_ready, alerts_table):
    ip = "10.34.0.6"
    process_message(CPU_93, ip)
    process_message(CPU_93, ip)

    alerts = alerts_table.by_type("CPU_HIGH")
    assert len(alerts) == 1
    assert alerts[0].event_count == 2
