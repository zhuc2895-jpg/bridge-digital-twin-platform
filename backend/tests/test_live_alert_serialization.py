import json
import time

from app.dependencies import create_services
from app.engine.data_engine import MonitoringEngine
from app.live_contract import LiveFrameSource, build_sensor_update
from app.live_stream import SensorUpdatePublisher
from app.ws.message_contract import encode_message
from tests.factories import reading
from tests.helpers import CapturingManager


def test_live_frame_uses_only_live_eligible_state():
    engine = MonitoringEngine()
    engine.ingest(
        [reading(sensor_id="LIVE", value=100.0, timestamp=100.0)],
        live_eligible=True,
    )
    engine.ingest(
        [reading(sensor_id="BACKFILL", value=900.0, timestamp=200.0)],
        live_eligible=False,
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

    payload = build_sensor_update(engine)

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
    publisher = SensorUpdatePublisher(services.engine, manager)

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

    message = encode_message(build_sensor_update(services.engine))
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

    payload = build_sensor_update(engine)

    assert len(payload["sensors"]) == 32
    assert {item["timestamp"] for item in payload["sensors"]} == set(range(8, 40))

def test_unpaired_surrogate_is_isolated_from_live_frame_encoding(tmp_path):
    engine = MonitoringEngine()
    engine.ingest(
        [reading(sensor_id="S01", name="bad\ud800name", value=100.0)],
        live_eligible=True,
    )

    payload = build_sensor_update(engine)
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

    alert = build_sensor_update(engine)["alerts"][0]

    assert alert["value"] == 400.0
    assert alert["threshold"] is None
    assert alert["timestamp"] is None
    assert alert["invalid"] is True

def test_overflow_keeps_newest_sensor_records(monkeypatch):
    engine = MonitoringEngine()
    engine.ingest(
        [
            reading(
                sensor_id=f"S{index:03d}",
                name="sensor-name-" * 20,
                value=float(index),
                timestamp=float(index),
            )
            for index in range(32)
        ],
        live_eligible=True,
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

    import app.live_contract as live_contract

    monkeypatch.setattr(live_contract, "MAX_SENSOR_UPDATE_BYTES", 6000)
    payload = build_sensor_update(engine)

    timestamps = [item["timestamp"] for item in payload["sensors"]]
    assert timestamps == sorted(timestamps, reverse=True)
    assert 31.0 in timestamps


def test_late_server_processing_drops_frame_without_enqueueing():
    services = create_services()
    manager = CapturingManager()
    publisher = SensorUpdatePublisher(
        services.engine,
        manager,
        max_frame_age_seconds=0.5,
    )
    source = LiveFrameSource(sensors=[], alerts=[], stats={})

    publisher.publish(
        source,
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

    alert = build_sensor_update(engine)["alerts"][0]

    assert alert["value"] is None
    assert alert["invalid"] is True


def test_slow_encoding_consumes_total_latency_budget(monkeypatch):
    services = create_services()
    manager = CapturingManager()
    publisher = SensorUpdatePublisher(
        services.engine,
        manager,
        max_frame_age_seconds=0.05,
    )
    source = LiveFrameSource(sensors=[], alerts=[], stats={})
    original_build = __import__(
        "app.live_stream", fromlist=["build_sensor_update_from_snapshot"]
    ).build_sensor_update_from_snapshot

    def slow_build(*args):
        time.sleep(0.06)
        return original_build(*args)

    import app.live_stream as live_stream

    monkeypatch.setattr(live_stream, "build_sensor_update_from_snapshot", slow_build)

    publisher.publish(source, generated_at=time.monotonic())

    assert manager.payloads == []
