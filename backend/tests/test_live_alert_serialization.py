import json
import threading
import time

import pytest
from app.dependencies import create_services
from app.engine.data_engine import MonitoringEngine
from app.ingestion import validate_live_json_records
from app.live_contract import (
    LiveSensorSnapshot,
    build_sensor_update_from_snapshot,
)
from app.live_stream import SensorUpdatePublisher, capture_live_snapshot
from app.sensor_batch import LiveEligibility, SensorBatch
from app.ws.message_contract import MAX_SENSOR_UPDATE_BYTES, encode_message

from tests.factories import reading
from tests.helpers import (
    CapturingManager,
    PublisherEnvironment,
    ingest_numbered_sensors,
    ingest_records,
)

_SHARED_LOCK = threading.RLock()


def _build(engine):
    return build_sensor_update_from_snapshot(
        capture_live_snapshot(engine, _SHARED_LOCK)
    )


def _publisher(
    engine,
    manager,
    *,
    lock=None,
    max_frame_age_seconds=0.5,
):
    return SensorUpdatePublisher(
        PublisherEnvironment(
            engine=engine,
            ws_manager=manager,
            processing_lock=lock or _SHARED_LOCK,
        ),
        max_frame_age_seconds=max_frame_age_seconds,
    )


def test_live_frame_uses_only_live_eligible_state():
    engine = MonitoringEngine()
    ingest_records(
        engine,
        [reading(sensor_id="LIVE", value=100.0, timestamp=100.0)],
    )
    ingest_records(
        engine,
        [reading(sensor_id="BACKFILL", value=900.0, timestamp=200.0)],
        live_eligibility=LiveEligibility.BACKFILL,
    )
    engine.submit_alert(
        sensor_id="LIVE",
        sensor_name="Live sensor",
        level="yellow",
        message="Live alert",
        value=400.0,
        threshold=300.0,
        source="rule",
        timestamp=100.0,
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
        timestamp=200.0,
        live_eligible=False,
    )

    payload = _build(engine)

    assert [item["sensor_id"] for item in payload["sensors"]] == ["LIVE"]
    assert [item["sensor_id"] for item in payload["alerts"]] == ["LIVE"]
    assert payload["alerts"][0]["invalid"] is False
    assert "details" not in payload["alerts"][0]


def test_malformed_alert_value_does_not_suppress_live_update(caplog):
    services = create_services()
    services.engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="Malformed AI value",
        value="not-a-number",
        threshold=300.0,
        source="ai_feature_arbitration",
        timestamp=1_700_000_000.0,
    )
    manager = CapturingManager()
    publisher = _publisher(services.engine, manager)

    publisher.publish()

    assert len(manager.payloads) == 1
    alert = manager.payloads[0]["alerts"][0]
    assert alert["value"] is None
    assert alert["invalid"] is True
    assert any("sensor_update" in record.message for record in caplog.records)


def test_non_finite_alert_value_produces_standard_json():
    services = create_services()
    services.engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="Non-finite AI value",
        value=float("nan"),
        threshold=300.0,
        source="ai_feature_arbitration",
        timestamp=1_700_000_000.0,
    )

    message = encode_message(_build(services.engine))
    payload = json.loads(
        message,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ),
    )

    assert payload["alerts"][0]["value"] is None
    assert payload["alerts"][0]["invalid"] is True


def test_live_frame_contains_at_most_thirty_two_live_sensors():
    engine = MonitoringEngine()
    ingest_numbered_sensors(engine)

    payload = _build(engine)

    assert len(payload["sensors"]) == 32
    assert {item["timestamp"] for item in payload["sensors"]} == set(range(8, 40))

def test_bounded_frame_preserves_distinct_sensor_identifiers(monkeypatch):
    first_id = "S" * 63 + "1"
    second_id = "S" * 63 + "2"
    engine = MonitoringEngine()
    ingest_records(
        engine,
        [
            reading(sensor_id=first_id, name="first-" * 20),
            reading(sensor_id=second_id, name="second-" * 20),
        ],
    )
    for sensor_id in (first_id, second_id):
        engine.submit_alert(
            sensor_id=sensor_id,
            sensor_name="AI detector",
            level="yellow",
            message="alert-" * 20,
            value=400.0,
            threshold=0.0,
            source="ai_feature_arbitration",
            timestamp=1_700_000_000.0,
        )

    import app.live_contract as live_contract

    monkeypatch.setattr(live_contract, "MAX_SENSOR_UPDATE_BYTES", 1100)
    payload = _build(engine)

    assert {item["sensor_id"] for item in payload["sensors"]} == {
        first_id,
        second_id,
    }
    assert {item["sensor_id"] for item in payload["alerts"]} == {
        first_id,
        second_id,
    }


def test_unpaired_surrogate_is_isolated_from_live_frame_encoding(tmp_path):
    engine = MonitoringEngine()
    ingest_records(
        engine,
        [reading(sensor_id="S01", name="bad\ud800name", value=100.0)],
    )

    payload = _build(engine)
    message = encode_message(payload)

    assert "\ufffd" in message
    assert payload["sensors"][0]["name"].endswith("name")


def test_invalid_alert_threshold_and_timestamp_are_null():
    engine = MonitoringEngine()
    engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="Invalid numbers",
        value=400.0,
        threshold=float("nan"),
        source="ai_feature_arbitration",
        timestamp=float("inf"),
    )

    alert = _build(engine)["alerts"][0]

    assert alert["value"] == 400.0
    assert alert["threshold"] is None
    assert alert["timestamp"] is None
    assert alert["invalid"] is True

def test_overflow_keeps_newest_sensor_records(monkeypatch):
    engine = MonitoringEngine()
    ingest_records(
        engine,
        [
            reading(
                sensor_id=f"S{index:03d}",
                name="sensor-name-" * 20,
                value=float(index),
                timestamp=float(index),
            )
            for index in range(32)
        ],
    )
    for index in range(20):
        engine.submit_alert(
            sensor_id=f"A{index:03d}",
            sensor_name="alert-name-" * 20,
            level="yellow",
            message="alert-message-" * 100,
            value=400.0,
            threshold=300.0,
            source="rule",
            timestamp=1_700_000_000.0 + index,
            live_eligible=True,
        )

    from app import live_contract

    monkeypatch.setattr(live_contract, "MAX_SENSOR_UPDATE_BYTES", 6000)
    payload = _build(engine)

    timestamps = [item["timestamp"] for item in payload["sensors"]]
    assert timestamps == sorted(timestamps, reverse=True)
    assert 31.0 in timestamps


def test_late_server_processing_drops_frame_without_enqueueing():
    services = create_services()
    manager = CapturingManager()
    publisher = _publisher(
        services.engine,
        manager,
        max_frame_age_seconds=0.5,
    )
    snapshot = LiveSensorSnapshot(sensors=[], alerts=[], stats={})

    publisher.publish(
        snapshot,
        generated_at=time.monotonic() - 1.0,
    )

    assert manager.payloads == []


def test_boolean_alert_value_is_invalid():
    engine = MonitoringEngine()
    engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="Boolean value",
        value=True,
        threshold=300.0,
        source="ai_feature_arbitration",
        timestamp=1_700_000_000.0,
    )

    alert = _build(engine)["alerts"][0]

    assert alert["value"] is None
    assert alert["invalid"] is True


def test_alert_without_timestamp_is_invalid():
    snapshot = LiveSensorSnapshot(
        sensors=[],
        alerts=[
            {
                "id": "alert-1",
                "sensor_id": "S01",
                "sensor_name": "AI detector",
                "level": "yellow",
                "message": "Missing event time",
                "value": 400.0,
                "threshold": 300.0,
                "source": "rule",
            }
        ],
        stats={},
    )

    alert = build_sensor_update_from_snapshot(snapshot)["alerts"][0]

    assert alert["timestamp"] is None
    assert alert["invalid"] is True


def test_invalid_alert_timestamp_does_not_suppress_later_frames():
    engine = MonitoringEngine()
    engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="Bad event time",
        value=400.0,
        threshold=0.0,
        source="ai_feature_arbitration",
        timestamp=None,
    )
    engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="Recovered event time",
        value=401.0,
        threshold=0.0,
        source="ai_feature_arbitration",
        timestamp=1_700_000_000.0,
    )

    payload = _build(engine)

    assert len(payload["alerts"]) == 2
    invalid = next(
        alert for alert in payload["alerts"] if alert["message"] == "Bad event time"
    )
    assert invalid["timestamp"] is None
    assert invalid["invalid"] is True


def test_rule_alert_with_nonpositive_threshold_is_invalid():
    snapshot = LiveSensorSnapshot(
        sensors=[],
        alerts=[
            {
                "id": "alert-1",
                "sensor_id": "S01",
                "sensor_name": "Rule detector",
                "level": "yellow",
                "message": "Missing physical threshold",
                "value": 400.0,
                "threshold": 0.0,
                "source": "rule",
                "timestamp": 1_700_000_000.0,
            }
        ],
        stats={},
    )

    alert = build_sensor_update_from_snapshot(snapshot)["alerts"][0]

    assert alert["threshold"] is None
    assert alert["invalid"] is True


def test_slow_encoding_consumes_total_latency_budget(monkeypatch):
    services = create_services()
    manager = CapturingManager()
    publisher = _publisher(
        services.engine,
        manager,
        max_frame_age_seconds=0.05,
    )
    snapshot = LiveSensorSnapshot(sensors=[], alerts=[], stats={})
    original_build = __import__(
        "app.live_stream", fromlist=["build_sensor_update_from_snapshot"]
    ).build_sensor_update_from_snapshot

    def slow_build(*args):
        time.sleep(0.06)
        return original_build(*args)

    from app import live_stream

    monkeypatch.setattr(live_stream, "build_sensor_update_from_snapshot", slow_build)

    publisher.publish(snapshot, generated_at=time.monotonic())

    assert manager.payloads == []

def test_external_update_is_not_consumed_when_frame_is_skipped():
    engine = MonitoringEngine()
    engine.ingest(
        SensorBatch(
            records=[reading(sensor_id="S01", value=900.0, timestamp=100.0)],
            live_eligibility=LiveEligibility.EXTERNAL,
        )
    )
    manager = CapturingManager()
    publisher = _publisher(engine, manager)

    publisher.publish(generated_at=time.monotonic() - 1.0)

    assert manager.payloads == []
    assert set(engine.get_pending_external_versions()) == {"S01"}


@pytest.mark.parametrize(
    "oversized_details",
    [False, True],
    ids=["long-text", "oversized-details"],
)
def test_bounded_sensor_update_preserves_complete_frame(oversized_details):
    services = create_services()
    for index in range(20):
        services.engine.submit_alert(
            sensor_id=f"ALERT-{index:02d}",
            sensor_name="告警" * 100,
            level="yellow",
            message="超限告警" * 500,
            value=400.0 + index,
            threshold=300.0,
            source="rule",
            timestamp=1_700_000_000.0 + index * 20,
            details=(
                {
                    "blob": "x" * 20_000,
                    "context": {"index": index},
                }
                if oversized_details
                else None
            ),
        )
    readings = [
        reading(
            sensor_id=f"S{index:02d}",
            name="传感器名称" * 500,
            value=100.0 + index,
            timestamp=1_700_000_000.0,
        )
        for index in range(8)
    ]
    ingest_records(services.engine, readings)

    payload = _build(services.engine)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    assert len(payload["sensors"]) == 8
    assert len(payload["alerts"]) == 20
    assert len(encoded) <= MAX_SENSOR_UPDATE_BYTES
    assert all("details" not in alert for alert in payload["alerts"])


def test_non_serializable_ai_details_do_not_escape_publishing():
    services = create_services()
    services.engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="AI evidence",
        value=400.0,
        threshold=300.0,
        source="ai_feature_arbitration",
        timestamp=1_700_000_000.0,
        details={"model_votes": {"stale", "confirm"}},
    )
    manager = CapturingManager()
    publisher = _publisher(
        services.engine,
        manager,
        lock=services.processing_lock,
    )

    publisher.publish()

    assert len(manager.payloads) == 1
    assert len(manager.payloads[0]["alerts"]) == 1
    assert "details" not in manager.payloads[0]["alerts"][0]


def test_live_readings_use_shared_strict_ingestion_rules():
    records = [
        reading(sensor_id="S01", value=100.0),
        reading(sensor_id="S02", value="101.0"),
        reading(sensor_id="S03", value=True),
        reading(sensor_id="S04", name="", value=102.0),
    ]

    normalized = validate_live_json_records(records)

    assert [item["sensor_id"] for item in normalized] == ["S01"]
