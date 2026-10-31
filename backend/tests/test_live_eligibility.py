from app.engine.data_engine import MonitoringEngine
from tests.factories import reading


def test_live_snapshot_ignores_newer_non_live_backfill():
    engine = MonitoringEngine()
    engine.ingest(
        [reading(sensor_id="S01", value=100.0, timestamp=100.0)],
        live_eligible=True,
    )
    engine.ingest(
        [reading(sensor_id="S01", value=900.0, timestamp=200.0)],
        live_eligible=False,
    )

    snapshot = engine.get_live_snapshot()

    assert len(snapshot) == 1
    assert snapshot[0]["sensor_id"] == "S01"
    assert snapshot[0]["value"] == 100.0
    assert engine.get_latest("S01")["value"] == 900.0


def test_live_snapshot_keeps_thirty_two_most_recent_sensors():
    engine = MonitoringEngine()
    engine.ingest(
        [
            reading(
                sensor_id=f"S{index:03d}",
                value=float(index),
                timestamp=float(index),
            )
            for index in range(40)
        ],
        live_eligible=True,
    )

    snapshot = engine.get_live_snapshot()

    assert len(snapshot) == 32
    assert {item["timestamp"] for item in snapshot} == set(range(8, 40))
    assert [item["timestamp"] for item in snapshot] == sorted(
        (item["timestamp"] for item in snapshot),
        reverse=True,
    )


def test_live_alerts_exclude_non_live_backfill_alerts():
    engine = MonitoringEngine()
    engine.submit_alert(
        sensor_id="LIVE",
        sensor_name="Live sensor",
        level="yellow",
        message="Live alert",
        value=400.0,
        threshold=300.0,
        source="rule",
        timestamp=1_700_000_000.0,
        live_eligible=True,
    )
    engine.submit_alert(
        sensor_id="BACKFILL",
        sensor_name="Backfill sensor",
        level="red",
        message="Backfill alert",
        value=800.0,
        threshold=600.0,
        source="rule",
        timestamp=1_700_000_001.0,
        live_eligible=False,
    )

    live_alerts = engine.get_recent_live_alerts()
    retained_alerts = engine.get_recent_alerts()

    assert [alert["sensor_id"] for alert in live_alerts] == ["LIVE"]
    assert {alert["sensor_id"] for alert in retained_alerts} == {
        "LIVE",
        "BACKFILL",
    }

def test_older_live_reading_cannot_replace_newer_live_reading():
    engine = MonitoringEngine()
    engine.ingest(
        [reading(sensor_id="S01", value=200.0, timestamp=200.0)],
        live_eligible=True,
    )
    engine.ingest(
        [reading(sensor_id="S01", value=100.0, timestamp=100.0)],
        live_eligible=True,
    )

    snapshot = engine.get_live_snapshot()

    assert snapshot[0]["value"] == 200.0
    assert snapshot[0]["timestamp"] == 200.0
