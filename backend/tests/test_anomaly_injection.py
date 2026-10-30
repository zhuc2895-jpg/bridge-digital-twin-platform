from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from fastapi.testclient import TestClient

from app.dependencies import create_services
from app.engine.simulator import DataSimulator
from app.main import create_app
from app.ml.contracts import BaseDetector, BaselineStatus
from app.ml.feature_arbitration import FeatureArbitrationDetector
from app.ml.voting import VotingDetector
from tests.factories import reading


class ReadyVotingModel(BaseDetector):
    def __init__(self, detector_id: str, source: str, *, anomalous: bool) -> None:
        self.detector_id = detector_id
        self.display_name = detector_id
        self.source = source
        self.anomalous = anomalous

    def learn_baseline(self, reading, *, is_normal=True):
        return self.get_baseline_status(reading["sensor_id"])

    def get_baseline_status(self, sensor_id=None):
        status = BaselineStatus(
            sensor_id=sensor_id or "S01",
            readings=100,
            required_readings=100,
            state="ready",
            mean=100.0,
            std=1.0,
            ema_fast=100.0,
            ema_slow=100.0,
        )
        if sensor_id is None:
            return {"S01": status}
        return status

    def reset_baseline(self, sensor_id=None):
        return None

    def detect_one(self, reading):
        return self.make_result(
            reading,
            anomalous=self.anomalous,
            score=0.9 if self.anomalous else 0.1,
            confidence=0.9 if self.anomalous else 0.1,
            reason="stub anomaly" if self.anomalous else "stub normal",
            details={"vote": self.anomalous, "model_ready": True},
        )

    def get_stats(self):
        return {"total_detections": 0, "ml_alerts_triggered": 0}


def _single_vote_arbitration_detector(normal_predicate):
    voting = VotingDetector(
        [
            ReadyVotingModel("stalwart", "ai_stalwart", anomalous=True),
            ReadyVotingModel("gan_ae", "ai_gan_ae", anomalous=False),
            ReadyVotingModel(
                "isolation_forest",
                "ai_isolation_forest",
                anomalous=False,
            ),
        ]
    )
    return FeatureArbitrationDetector(
        voting,
        normal_predicate=normal_predicate,
    )


class OneShotInjectionSimulator(DataSimulator):
    def __init__(self, frame_timestamp: float) -> None:
        super().__init__()
        self.frame_timestamp = frame_timestamp

    async def generate(self):
        self.is_running = True
        try:
            yield self.next_readings(timestamp=self.frame_timestamp)
        finally:
            self.is_running = False


def _set_normal_values(monkeypatch):
    monkeypatch.setattr(
        "app.engine.simulator.np.random.normal",
        lambda loc, scale: loc,
    )


def _set_uniform_sequence(monkeypatch, *values):
    sequence = iter(values)
    expected_ranges = {
        (2.5, 4.0),
        (50.0, 150.0),
    }

    def uniform(low, high):
        value = next(sequence)
        assert (low, high) in expected_ranges
        assert low <= value <= high
        return value

    monkeypatch.setattr("app.engine.simulator.random.uniform", uniform)


def _reading_for(frame: list[dict], sensor_id: str) -> dict:
    return next(item for item in frame if item["sensor_id"] == sensor_id)


def _run_concurrently(*operations):
    barrier = threading.Barrier(len(operations) + 1)

    def run(operation):
        barrier.wait()
        return operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, operation) for operation in operations]
        barrier.wait()
        return [future.result(timeout=2) for future in futures]


def test_inject_anomaly_rejects_missing_sensor_identifier(app, client):
    response = client.post("/api/analysis/inject-anomaly")

    assert response.status_code == 400
    assert app.state.services.simulator.pending_injection_count() == 0


def test_inject_anomaly_rejects_unknown_sensor_with_400(app, client):
    response = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "UNKNOWN"},
    )

    assert response.status_code == 400
    assert "UNKNOWN" in response.json()["detail"]
    assert app.state.services.simulator.pending_injection_count("S01") == 0


def test_inject_anomaly_rejects_conflicting_identifier_sources(app, client):
    response = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "S01"},
        json={"sensor_id": "S02"},
    )

    assert response.status_code == 400
    assert app.state.services.simulator.pending_injection_count() == 0


def test_injected_reading_uses_configured_ranges_once_then_recovers(
    app,
    client,
    monkeypatch,
):
    simulator = app.state.services.simulator
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)

    response = client.post(
        "/api/analysis/inject-anomaly",
        json={"sensor_id": "S01"},
    )

    injected_tick = simulator.next_readings(timestamp=1000.0)
    recovered_tick = simulator.next_readings(timestamp=1001.0)
    injected = _reading_for(injected_tick, "S01")
    recovered = _reading_for(recovered_tick, "S01")

    assert response.status_code == 200
    assert response.json()["sensor_id"] == "S01"
    assert injected["value"] == pytest.approx(550.0)
    assert recovered["value"] == pytest.approx(200.0)
    assert simulator.pending_injection_count("S01") == 0


def test_consecutive_injections_are_consumed_in_order_without_contamination(
    app,
    client,
    monkeypatch,
):
    simulator = app.state.services.simulator
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0, 4.0, 150.0)

    first = client.post("/api/analysis/inject-anomaly?sensor_id=S01")
    second = client.post("/api/analysis/inject-anomaly?sensor_id=S01")
    first_tick = simulator.next_readings(timestamp=1000.0)
    second_tick = simulator.next_readings(timestamp=1001.0)
    third_tick = simulator.next_readings(timestamp=1002.0)

    assert first.status_code == 200
    assert second.status_code == 200
    assert _reading_for(first_tick, "S01")["value"] == pytest.approx(550.0)
    assert _reading_for(second_tick, "S01")["value"] == pytest.approx(950.0)
    assert _reading_for(third_tick, "S01")["value"] == pytest.approx(200.0)
    assert all(
        item["value"] == pytest.approx(
            next(
                sensor["normal_mean"]
                for sensor in DataSimulator.SENSORS
                if sensor["id"] == item["sensor_id"]
            )
        )
        for item in third_tick
        if item["sensor_id"] != "S08"
    )
    assert simulator.pending_injection_count("S01") == 0


def test_injection_requested_during_frame_applies_to_next_frame(monkeypatch):
    simulator = DataSimulator()
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)
    frame_started = threading.Event()
    injection_started = threading.Event()
    release_frame = threading.Event()

    def paused_normal_value(sensor):
        if sensor["id"] == "S01" and not frame_started.is_set():
            frame_started.set()
            assert release_frame.wait(timeout=2)
        return float(sensor["normal_mean"])

    monkeypatch.setattr(
        simulator,
        "_generate_normal_value",
        paused_normal_value,
    )

    def request_injection():
        injection_started.set()
        return simulator.inject_anomaly("S01")

    with ThreadPoolExecutor(max_workers=2) as pool:
        frame_future = pool.submit(simulator.next_readings, 1000.0)
        assert frame_started.wait(timeout=1)
        injection_future = pool.submit(request_injection)
        assert injection_started.wait(timeout=1)
        threading.Timer(0.05, release_frame.set).start()

        first_frame = frame_future.result(timeout=2)
        injection_future.result(timeout=2)
        second_frame = simulator.next_readings(timestamp=1001.0)

    assert _reading_for(first_frame, "S01")["value"] == pytest.approx(200.0)
    assert _reading_for(second_frame, "S01")["value"] == pytest.approx(550.0)
    assert simulator.pending_injection_count("S01") == 0


def test_concurrent_injections_are_queued_atomically(monkeypatch):
    simulator = DataSimulator()
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0, 4.0, 150.0)

    _run_concurrently(
        lambda: simulator.inject_anomaly("S01"),
        lambda: simulator.inject_anomaly("S01"),
    )

    assert simulator.pending_injection_count("S01") == 2
    assert _reading_for(
        simulator.next_readings(timestamp=1000.0),
        "S01",
    )["value"] == pytest.approx(550.0)
    assert _reading_for(
        simulator.next_readings(timestamp=1001.0),
        "S01",
    )["value"] == pytest.approx(950.0)
    assert simulator.pending_injection_count("S01") == 0


def test_concurrent_frames_consume_each_injection_exactly_once(monkeypatch):
    simulator = DataSimulator()
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0, 4.0, 150.0)
    simulator.inject_anomaly("S01")
    simulator.inject_anomaly("S01")

    frames = _run_concurrently(
        lambda: simulator.next_readings(timestamp=1000.0),
        lambda: simulator.next_readings(timestamp=1001.0),
    )

    injected_values = sorted(
        _reading_for(frame, "S01")["value"]
        for frame in frames
    )
    assert injected_values == pytest.approx([550.0, 950.0])
    assert simulator.pending_injection_count("S01") == 0


def test_injected_reading_runs_websocket_processing_and_is_queryable(monkeypatch):
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)
    base = 1_700_000_000.0
    services = create_services()
    services.detectors.replace_detector(
        _single_vote_arbitration_detector(
            services.engine.is_normal_reading
        )
    )
    services.simulator = OneShotInjectionSimulator(base)
    app = create_app(services)

    with TestClient(app) as client:
        baseline = [
            reading(
                value=100.0 + (index % 2),
                timestamp=base - 100 + index,
            )
            for index in range(80)
        ]
        upload = client.post(
            "/api/data/upload/json?push_live=false",
            json=baseline,
        )
        injection = client.post(
            "/api/analysis/inject-anomaly",
            params={"sensor_id": "S01"},
        )
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()

        recent = client.get("/api/alerts/").json()["alerts"]
        ranged = client.get(
            "/api/sensors/history/alerts",
            params={"start": base, "end": base},
        ).json()["alerts"]
        detector_stats = client.get("/api/analysis/detectors").json()

    injected = _reading_for(payload["sensors"], "S01")
    matching = [
        alert
        for alert in recent
        if alert["sensor_id"] == "S01" and alert["timestamp"] == base
    ]
    rule_alert = next(alert for alert in matching if alert["source"] == "rule")
    ai_alert = next(
        alert
        for alert in matching
        if alert["source"] == "ai_feature_arbitration"
    )

    assert upload.status_code == 200
    assert injection.status_code == 200
    assert injected["value"] == pytest.approx(550.0)
    assert matching
    assert rule_alert["level"] == "orange"
    assert rule_alert["value"] == pytest.approx(550.0)
    assert ai_alert["value"] == pytest.approx(550.0)
    assert ai_alert["details"]["final_conclusion"] == "confirmed"
    assert ai_alert["details"]["triggered_models"] == ["stalwart"]
    assert matching == ranged
    ensemble_stats = detector_stats["detectors"][0]["stats"]
    assert ensemble_stats["layers"] == [
        "model_voting",
        "feature_arbitration",
    ]
    assert detector_stats["total_detections"] > 0
    assert ensemble_stats["arbitration"]["confirmed_decisions"] >= 1
