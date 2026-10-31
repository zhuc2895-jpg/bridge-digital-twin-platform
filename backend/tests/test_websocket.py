from contextlib import ExitStack
import json
import logging
import threading
import time

from fastapi.testclient import TestClient

from app.dependencies import create_services
from app.live_stream import MAX_SENSOR_UPDATE_BYTES
from app.main import create_app
from tests.factories import reading


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
        )


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()

def test_websocket_stats_expose_retained_alert_count():
    services = create_services()
    services.live_stream_autostart = False
    services.simulator = OneShotSimulator()
    app = create_app(services)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()

    assert payload["type"] == "sensor_update"
    assert payload["stats"]["retained_alerts"] == 0
    assert "recent_alerts" not in payload["stats"]
    assert "active_alerts" not in payload["stats"]


def test_live_stream_runs_without_websocket_clients():
    services = create_services()
    app = create_app(services)

    with TestClient(app) as client:
        assert _wait_until(lambda: services.engine.get_sensor_count() == 8)
        assert services.is_live_stream_running is True
        assert client.get("/api/health").json()["simulator_running"] is True

    assert services.is_live_stream_running is False
    assert services.simulator.is_running is False


def test_ten_websocket_clients_share_one_simulator_frame():
    services = create_services()
    services.live_stream_autostart = False
    services.simulator = CountingSimulator()
    services.live_stream_interval_seconds = 60.0
    app = create_app(services)

    with TestClient(app) as client, ExitStack() as stack:
        websockets = [
            stack.enter_context(client.websocket_connect("/ws/live"))
            for _ in range(10)
        ]
        payloads = [websocket.receive_json() for websocket in websockets]

        assert services.simulator.calls == 1
        assert services.engine.get_stats()["total_readings"] == 2
        assert services.engine.get_alert_count() == 1
        assert len(payloads[0]["alerts"]) == 1
        assert services.ws_manager.connection_count == 10
        assert all(payload == payloads[0] for payload in payloads)
        assert payloads[0]["type"] == "sensor_update"
        assert [item["sensor_id"] for item in payloads[0]["sensors"]] == ["S01", "S02"]

    assert services.ws_manager.active_connections == []
    assert services.simulator.is_running is False
    assert services.is_live_stream_running is False


def test_sensor_update_contract_contains_recent_twenty_alerts_within_10kb():
    services = create_services()
    services.live_stream_autostart = False
    services.simulator = OneShotSimulator()
    services.live_stream_interval_seconds = 60.0
    _add_twenty_alerts(services, long_messages=True)
    app = create_app(services)

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
        }
        for alert in payload["alerts"]
    )
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(encoded) <= MAX_SENSOR_UPDATE_BYTES


def test_bad_live_reading_is_skipped_and_next_frame_is_delivered(caplog):
    services = create_services()
    services.live_stream_autostart = False
    services.simulator = BadThenGoodSimulator()
    services.live_stream_interval_seconds = 0.02
    app = create_app(services)

    with caplog.at_level(logging.WARNING, logger="app.dependencies"):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/live") as websocket:
                first = websocket.receive_json()
                second = websocket.receive_json()

    assert [item["sensor_id"] for item in first["sensors"]] == ["S01"]
    assert [item["sensor_id"] for item in second["sensors"]] == ["S02"]
    assert any("Skipping invalid live reading" in record.message for record in caplog.records)


def test_processor_failure_is_logged_and_later_frames_continue(caplog):
    services = create_services()
    services.live_stream_autostart = False
    services.simulator = CountingSimulator()
    services.live_stream_interval_seconds = 0.02
    services.processor = FlakyProcessor(services.processor)
    app = create_app(services)

    with caplog.at_level(logging.ERROR, logger="app.dependencies"):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/live") as websocket:
                first = websocket.receive_json()
                second = websocket.receive_json()

    assert first["type"] == "sensor_update"
    assert second["type"] == "sensor_update"
    assert services.processor.calls >= 2
    assert services.engine.get_stats()["total_readings"] >= 2
    assert any("pipeline failed" in record.message for record in caplog.records)


def test_first_frame_latency_and_one_hz_cadence():
    services = create_services()
    services.live_stream_autostart = False
    app = create_app(services)

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
    services = create_services()
    app = create_app(services)

    with TestClient(app) as client:
        assert _wait_until(lambda: services.engine.get_sensor_count() == 8)
        time.sleep(0.55)
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()
            received_at = time.time()

    generation_to_receipt = received_at - payload["sensors"][0]["timestamp"]
    assert 0 <= generation_to_receipt < 0.5


def test_repeated_connect_disconnect_cleans_up_registry():
    services = create_services()
    services.live_stream_autostart = False
    services.simulator = OneShotSimulator()
    services.live_stream_interval_seconds = 60.0
    app = create_app(services)

    with TestClient(app) as client:
        for _ in range(10):
            with client.websocket_connect("/ws/live") as websocket:
                assert websocket.receive_json()["type"] == "sensor_update"
            assert _wait_until(lambda: services.ws_manager.connection_count == 0)
            assert services.is_live_stream_running is True

    assert services.ws_manager.active_connections == []
    assert services.simulator.is_running is False
