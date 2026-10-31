from contextlib import ExitStack
import json
import logging
import threading
import time

from fastapi.testclient import TestClient

from app.dependencies import create_services
from app.live_contract import (
    MAX_SENSOR_UPDATE_BYTES,
    build_sensor_update,
    normalize_live_readings,
)
from app.live_stream import SensorUpdatePublisher
from tests.factories import reading
from tests.helpers import CapturingManager, TrackingLock, create_live_app, wait_until


class OneShotSimulator:
    is_running = False

    def next_readings(self, timestamp=None):
        self.is_running = False
        return [reading(timestamp=timestamp or 1_700_000_000.0)]


class CountingSimulator:
    is_running = False

    def __init__(self):
        self.calls = 0
        self._lock = threading.Lock()

    def next_readings(self, timestamp=None):
        with self._lock:
            self.calls += 1
            call = self.calls
        return [
            reading(sensor_id="S01", value=600.0 + call, timestamp=1000.0 + call),
            reading(sensor_id="S02", value=200.0 + call, timestamp=1000.0 + call),
        ]


class GatedCountingSimulator:
    is_running = False

    def __init__(self):
        self.calls = 0
        self.release = threading.Event()

    def next_readings(self, timestamp=None):
        if not self.release.wait(timeout=5.0):
            raise RuntimeError("test simulator gate was not released")
        self.calls += 1
        now = time.time()
        return [
            reading(
                sensor_id=f"S{index:02d}",
                name=f"Sensor {index}",
                value=100.0 + index + self.calls,
                timestamp=now,
            )
            for index in range(1, 9)
        ]


class BadThenGoodSimulator:
    is_running = False

    def __init__(self):
        self.calls = 0

    def next_readings(self, timestamp=None):
        self.calls += 1
        if self.calls == 1:
            return [
                reading(sensor_id="S01", value=101.0, timestamp=1001.0),
                {
                    "sensor_id": "S02",
                    "name": "bad reading",
                    "type": "strain",
                    "value": 10**10000,
                    "timestamp": 1001.0,
                },
            ]
        return [reading(sensor_id="S02", value=202.0, timestamp=1002.0)]


class FlakyProcessor:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = 0

    def process(self, records):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("detector pipeline exploded")
        return self.delegate.process(records)


def _add_twenty_alerts(services, *, long_messages: bool = False):
    for index in range(20):
        services.engine.submit_alert(
            sensor_id=f"ALERT-{index:02d}",
            sensor_name=f"告警传感器 {index}",
            level="yellow",
            message="超限告警" * 200 if long_messages else f"告警 {index}",
            value=400.0 + index,
            threshold=300.0,
            source="rule",
            timestamp=1_700_000_000.0 + index * 20,
            details={
                "case": index,
                "evidence": {"source": "threshold", "sequence": index},
            },
        )


def test_websocket_stats_expose_retained_alert_count():
    services, app = create_live_app(simulator=OneShotSimulator())

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()

    assert payload["type"] == "sensor_update"
    assert payload["stats"]["retained_alerts"] == 0
    assert "recent_alerts" not in payload["stats"]
    assert "active_alerts" not in payload["stats"]


def test_live_stream_runs_without_websocket_clients():
    services, app = create_live_app(autostart=True)

    with TestClient(app) as client:
        assert wait_until(lambda: services.engine.get_sensor_count() == 8)
        assert services.live_stream.is_running is True
        assert client.get("/api/health").json()["simulator_running"] is True

    assert services.live_stream.is_running is False
    assert services.simulator.is_running is False


def test_ten_websocket_clients_receive_identical_complete_live_frames():
    simulator = GatedCountingSimulator()
    services, app = create_live_app(
        simulator=simulator,
        interval_seconds=1.0,
    )
    _add_twenty_alerts(services)

    with TestClient(app) as client, ExitStack() as stack:
        websockets = [
            stack.enter_context(client.websocket_connect("/ws/live"))
            for _ in range(10)
        ]
        simulator.release.set()

        generation_times = []
        for _ in range(3):
            payloads = [websocket.receive_json() for websocket in websockets]
            received_at = time.time()
            generation_times.append(payloads[0]["sensors"][0]["timestamp"])

            assert all(payload == payloads[0] for payload in payloads)
            assert len(payloads[0]["sensors"]) == 8
            assert len(payloads[0]["alerts"]) == 20
            assert all("details" not in alert for alert in payloads[0]["alerts"])
            assert all("invalid" in alert for alert in payloads[0]["alerts"])
            assert all(
                received_at - item["timestamp"] < 0.5
                for item in payloads[0]["sensors"]
            )

        assert all(
            previous + 0.8 <= current <= previous + 1.5
            for previous, current in zip(generation_times, generation_times[1:])
        )
        with services.processing_lock:
            calls = simulator.calls
            total_readings = services.engine.get_stats()["total_readings"]
            alert_count = services.engine.get_alert_count()

        assert total_readings == calls * 8
        assert alert_count == 20
        assert services.ws_manager.connection_count == 10

    assert services.ws_manager.active_connections == []
    assert services.simulator.is_running is False
    assert services.live_stream.is_running is False


def test_shared_state_mutations_use_processing_lock():
    services, app = create_live_app()
    lock = TrackingLock()
    services.processing_lock = lock

    with TestClient(app) as client:
        client.post(
            "/api/data/upload/json?push_live=false",
            json=[reading()],
        )

        before = lock.acquisitions
        thresholds = client.post(
            "/api/data/config/thresholds",
            params={"strain_yellow": 301.0},
        )
        assert thresholds.status_code == 200
        assert lock.acquisitions > before

        before = lock.acquisitions
        relearn = client.post(
            "/api/analysis/detectors/relearn",
            params={"sensor_id": "S01"},
        )
        assert relearn.status_code == 200
        assert lock.acquisitions > before


def test_live_payload_is_built_while_processing_lock_is_held():
    services, app = create_live_app(simulator=OneShotSimulator())
    lock = TrackingLock()
    services.processing_lock = lock
    original = services.engine.get_live_snapshot
    observed: list[bool] = []

    def tracked_live_snapshot(*args, **kwargs):
        observed.append(lock.held)
        return original(*args, **kwargs)

    services.engine.get_live_snapshot = tracked_live_snapshot

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            websocket.receive_json()

    assert observed
    assert all(observed)


class CurrentTimeCountingSimulator:
    is_running = False

    def __init__(self):
        self.calls = 0

    def next_readings(self, timestamp=None):
        self.calls += 1
        now = time.time()
        return [
            reading(
                sensor_id="S01",
                value=100.0 + self.calls,
                timestamp=now,
            ),
            reading(
                sensor_id="S02",
                value=200.0 + self.calls,
                timestamp=now,
            ),
        ]


def test_live_upload_for_existing_sensor_appears_in_next_frame():
    services, app = create_live_app(
        simulator=CountingSimulator(),
        interval_seconds=0.05,
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            websocket.receive_json()
            upload = client.post(
                "/api/data/upload/json?push_live=true",
                json=[
                    reading(
                        sensor_id="S01",
                        value=900.0,
                        timestamp=time.time(),
                    )
                ],
            )
            payload = websocket.receive_json()

    assert upload.status_code == 200
    s01 = next(item for item in payload["sensors"] if item["sensor_id"] == "S01")
    assert s01["value"] == 900.0


def test_live_frame_includes_only_live_eligible_external_sensors():
    services, app = create_live_app(
        simulator=CountingSimulator(),
        interval_seconds=0.05,
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            websocket.receive_json()
            live_upload = client.post(
                "/api/data/upload/json?push_live=true",
                json=[
                    reading(
                        sensor_id="LIVE-EXT",
                        value=123.0,
                        timestamp=time.time(),
                    )
                ],
            )
            backfill_upload = client.post(
                "/api/data/upload/json?push_live=false",
                json=[
                    reading(
                        sensor_id="BACKFILL-EXT",
                        value=456.0,
                        timestamp=time.time(),
                    )
                ],
            )
            payload = websocket.receive_json()

    assert live_upload.status_code == 200
    assert backfill_upload.status_code == 200
    sensor_ids = {item["sensor_id"] for item in payload["sensors"]}
    assert "LIVE-EXT" in sensor_ids
    assert "BACKFILL-EXT" not in sensor_ids


def test_sensor_update_contract_contains_recent_twenty_alerts_within_10kb():
    services, app = create_live_app(
        simulator=OneShotSimulator(),
        interval_seconds=60.0,
    )
    _add_twenty_alerts(services, long_messages=True)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()

    assert set(payload) == {"type", "sensors", "alerts", "stats"}
    assert payload["type"] == "sensor_update"
    assert len(payload["sensors"]) == 1
    assert len(payload["alerts"]) == 20
    assert payload["stats"]["retained_alerts"] == 20
    assert all(
        set(alert) == {
            "id",
            "sensor_id",
            "sensor_name",
            "level",
            "message",
            "value",
            "threshold",
            "source",
            "timestamp",
            "invalid",
        }
        for alert in payload["alerts"]
    )
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(encoded) <= MAX_SENSOR_UPDATE_BYTES


def test_bounded_sensor_update_keeps_all_twenty_alerts_and_sensor_frame():
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
    services.engine.ingest(readings, live_eligible=True)

    payload = build_sensor_update(services.engine)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    assert len(payload["sensors"]) == 8
    assert len(payload["alerts"]) == 20
    assert len(encoded) <= MAX_SENSOR_UPDATE_BYTES


def test_oversized_alert_details_are_bounded_without_dropping_records():
    services = create_services()
    for index in range(20):
        services.engine.submit_alert(
            sensor_id=f"ALERT-{index:02d}",
            sensor_name=f"Alert source {index}",
            level="yellow",
            message=f"Alert {index}",
            value=400.0 + index,
            threshold=300.0,
            source="rule",
            timestamp=1_700_000_000.0 + index * 20,
            details={
                "blob": "x" * 20_000,
                "context": {"index": index},
            },
        )
    readings = [
        reading(sensor_id=f"S{index:02d}", value=100.0 + index)
        for index in range(8)
    ]
    services.engine.ingest(readings, live_eligible=True)

    payload = build_sensor_update(services.engine)
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
    publisher = SensorUpdatePublisher(services.engine, manager)

    publisher.publish()

    assert len(manager.payloads) == 1
    assert len(manager.payloads[0]["alerts"]) == 1
    assert "details" not in manager.payloads[0]["alerts"][0]


def test_live_websocket_pushes_bounded_frame_with_oversized_alert_details():
    services, app = create_live_app(
        simulator=OneShotSimulator(),
        interval_seconds=60.0,
    )
    for index in range(20):
        services.engine.submit_alert(
            sensor_id=f"ALERT-{index:02d}",
            sensor_name=f"Alert source {index}",
            level="yellow",
            message=f"Alert {index}",
            value=400.0 + index,
            threshold=300.0,
            source="rule",
            timestamp=1_700_000_000.0 + index * 20,
            details={"blob": "x" * 20_000},
        )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(payload["alerts"]) == 20
    assert len(encoded) <= MAX_SENSOR_UPDATE_BYTES
    assert all("details" not in alert for alert in payload["alerts"])


def test_live_readings_use_shared_strict_ingestion_rules():
    records = [
        reading(sensor_id="S01", value=100.0),
        reading(sensor_id="S02", value="101.0"),
        reading(sensor_id="S03", value=True),
        reading(sensor_id="S04", name="", value=102.0),
    ]

    normalized = normalize_live_readings(records)

    assert [item["sensor_id"] for item in normalized] == ["S01"]


def test_bad_live_reading_is_skipped_and_next_frame_is_delivered(caplog):
    services, app = create_live_app(
        simulator=BadThenGoodSimulator(),
        interval_seconds=0.02,
    )

    with caplog.at_level(logging.WARNING, logger="app.live_contract"):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/live") as websocket:
                first = websocket.receive_json()
                second = websocket.receive_json()

    assert [item["sensor_id"] for item in first["sensors"]] == ["S01"]
    assert [item["sensor_id"] for item in second["sensors"]] == ["S02", "S01"]
    assert any("Skipping invalid live reading" in record.message for record in caplog.records)


def test_processor_failure_is_logged_and_later_frames_continue(caplog):
    services, app = create_live_app(
        simulator=CountingSimulator(),
        interval_seconds=0.02,
    )
    services.processor = FlakyProcessor(services.processor)

    with caplog.at_level(logging.ERROR, logger="app.live_stream"):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/live") as websocket:
                first = websocket.receive_json()
                second = websocket.receive_json()

    assert first["type"] == "sensor_update"
    assert second["type"] == "sensor_update"
    assert services.processor.calls >= 2
    assert services.engine.get_stats()["total_readings"] >= 2
    assert any("pipeline failed" in record.message for record in caplog.records)


def test_live_frame_encoding_runs_outside_processing_lock(monkeypatch):
    services, app = create_live_app(simulator=OneShotSimulator())
    lock = TrackingLock()
    services.processing_lock = lock
    observed: list[bool] = []

    import app.live_contract as live_contract

    original_encode = live_contract.encode_message

    def tracked_encode(payload):
        observed.append(lock.held)
        return original_encode(payload)

    monkeypatch.setattr(live_contract, "encode_message", tracked_encode)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            websocket.receive_json()

    assert observed
    assert all(held is False for held in observed)


def test_first_frame_latency_and_one_hz_cadence():
    services, app = create_live_app()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            first = websocket.receive_json()
            received_at = time.time()
            second_started = time.perf_counter()
            websocket.receive_json()
            second_interval = time.perf_counter() - second_started

    generation_to_receipt = received_at - first["sensors"][0]["timestamp"]
    assert 0 <= generation_to_receipt < 0.5
    assert 0.8 <= second_interval <= 1.5


def test_late_client_does_not_receive_a_stale_cached_frame():
    services, app = create_live_app(autostart=True)

    with TestClient(app) as client:
        assert wait_until(lambda: services.engine.get_sensor_count() == 8)
        time.sleep(0.55)
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()
            received_at = time.time()

    generation_to_receipt = received_at - payload["sensors"][0]["timestamp"]
    assert 0 <= generation_to_receipt < 0.5


def test_repeated_connect_disconnect_cleans_up_registry():
    services, app = create_live_app(
        simulator=OneShotSimulator(),
        interval_seconds=0.05,
    )

    with TestClient(app) as client:
        for _ in range(10):
            with client.websocket_connect("/ws/live") as websocket:
                assert websocket.receive_json()["type"] == "sensor_update"
            assert wait_until(lambda: services.ws_manager.connection_count == 0)
            assert services.live_stream.is_running is True

    assert services.ws_manager.active_connections == []
    assert services.simulator.is_running is False
