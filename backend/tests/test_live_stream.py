import time

from fastapi.testclient import TestClient

from tests.factories import reading
from tests.helpers import (
    CapturingManager,
    OneShotSimulator,
    TrackingLock,
    create_live_app,
    wait_until,
)


def test_live_stream_runs_without_websocket_clients():
    services, app = create_live_app(autostart=True)

    with TestClient(app) as client:
        assert wait_until(lambda: services.engine.get_sensor_count() == 8)
        assert services.live_stream.is_running is True
        assert client.get("/api/health").json()["simulator_running"] is True

    assert services.live_stream.is_running is False
    assert services.simulator.is_running is False


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


def test_live_snapshot_is_captured_while_processing_lock_is_held():
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


def test_live_tick_pipeline_uses_replaced_websocket_manager():
    services, _ = create_live_app(simulator=OneShotSimulator())
    manager = CapturingManager()
    services.ws_manager = manager

    services.live_tick.run_once(time.monotonic())

    assert len(manager.payloads) == 1
    assert manager.payloads[0]["type"] == "sensor_update"


def test_live_tick_pipeline_uses_replaced_processing_lock():
    services, _ = create_live_app(simulator=OneShotSimulator())
    lock = TrackingLock()
    services.processing_lock = lock

    services.live_tick.run_once(time.monotonic())

    assert lock.acquisitions > 0
