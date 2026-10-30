from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from fastapi.testclient import TestClient

from app.dependencies import create_services
from app.engine.simulator import (
    DataSimulator,
    SimulatorReading,
    UnknownSimulatorSensorError,
)
from app.main import create_app
from app.ml.contracts import BaseDetector, BaselineStatus
from app.ml.feature_arbitration import FeatureArbitrationDetector
from app.ml.voting import VotingDetector
from app.sensor_ids import SensorIdentifier
from tests.factories import reading


S01 = SensorIdentifier("S01")


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


def test_inject_anomaly_normalizes_valid_identifier_whitespace(app, client):
    response = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": " S01 "},
    )

    assert response.status_code == 200
    assert response.json()["sensor_id"] == "S01"


def test_inject_anomaly_rejects_conflicting_identifier_sources(app, client):
    response = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "S01"},
        json={"sensor_id": "S02"},
    )

    assert response.status_code == 400


def test_inject_anomaly_rejects_unknown_sensor_with_400(app, client):
    response = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "UNKNOWN"},
    )

    assert response.status_code == 400
    assert "UNKNOWN" in response.json()["detail"]


def test_inject_anomaly_accepts_json_body_identifier(app, client):
    response = client.post(
        "/api/analysis/inject-anomaly",
        json={"sensor_id": "S01"},
    )

    assert response.status_code == 200
    assert response.json()["sensor_id"] == "S01"


def test_inject_anomaly_triggers_queryable_alert_without_websocket(
    app,
    client,
    monkeypatch,
):
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)

    response = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "S01"},
    )
    recent = client.get("/api/alerts/").json()["alerts"]
    rule_alert = next(
        alert
        for alert in recent
        if alert["sensor_id"] == "S01" and alert["source"] == "rule"
    )
    ranged = client.get(
        "/api/sensors/history/alerts",
        params={
            "start": rule_alert["timestamp"],
            "end": rule_alert["timestamp"],
        },
    ).json()["alerts"]

    assert response.status_code == 200
    assert response.json()["message"] == "已生成并处理传感器 S01 的下一条注入读数"
    assert app.state.services.engine.get_stats()["total_readings"] == 1
    assert set(client.get("/api/sensors/").json()) == {"S01"}
    assert rule_alert["value"] == pytest.approx(550.0)
    assert rule_alert in ranged


def test_explicit_injection_metadata_matches_generated_reading(monkeypatch):
    simulator = DataSimulator()
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)

    generated = simulator.inject_anomaly(S01)

    assert generated.reading.value == pytest.approx(550.0)
    assert generated.injection.offset == pytest.approx(50.0)


def test_concurrent_http_injections_process_one_reading_each(
    app,
    client,
    monkeypatch,
):
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0, 4.0, 150.0)

    responses = _run_concurrently(
        lambda: client.post(
            "/api/analysis/inject-anomaly",
            params={"sensor_id": "S01"},
        ),
        lambda: client.post(
            "/api/analysis/inject-anomaly",
            params={"sensor_id": "S01"},
        ),
    )

    assert all(response.status_code == 200 for response in responses)
    assert {
        response.json()["injection"]["offset"] for response in responses
    } == {50.0, 150.0}
    assert app.state.services.engine.get_stats()["total_readings"] == 2
    assert set(client.get("/api/sensors/").json()) == {"S01"}
    rule_alerts = [
        alert
        for alert in client.get("/api/alerts/").json()["alerts"]
        if alert["sensor_id"] == "S01" and alert["source"] == "rule"
    ]
    assert sorted(alert["value"] for alert in rule_alerts) == pytest.approx(
        [550.0, 950.0]
    )


def test_consecutive_http_injections_are_consumed_once_each(
    app,
    client,
    monkeypatch,
):
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0, 4.0, 150.0)

    first = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "S01"},
    )
    second = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "S01"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert app.state.services.engine.get_stats()["total_readings"] == 2
    assert set(client.get("/api/sensors/").json()) == {"S01"}
    rule_alerts = [
        alert
        for alert in client.get("/api/alerts/").json()["alerts"]
        if alert["sensor_id"] == "S01" and alert["source"] == "rule"
    ]
    assert sorted(alert["value"] for alert in rule_alerts) == pytest.approx(
        [550.0, 950.0]
    )


def test_same_level_injections_respect_alert_cooldown(
    app,
    client,
    monkeypatch,
):
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0, 2.5, 50.0)

    first = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "S01"},
    )
    second = client.post(
        "/api/analysis/inject-anomaly",
        params={"sensor_id": "S01"},
    )

    rule_alerts = [
        alert
        for alert in client.get("/api/alerts/").json()["alerts"]
        if alert["sensor_id"] == "S01" and alert["source"] == "rule"
    ]

    assert first.status_code == 200
    assert second.status_code == 200
    assert app.state.services.engine.get_stats()["total_readings"] == 2
    assert len(rule_alerts) == 1
    assert rule_alerts[0]["value"] == pytest.approx(550.0)


def test_injected_reading_uses_configured_ranges_once_then_recovers(
    monkeypatch,
):
    simulator = DataSimulator()
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)

    generated = simulator.inject_anomaly(S01)
    recovered_tick = simulator.next_readings(timestamp=1001.0)
    recovered = _reading_for(recovered_tick, "S01")

    assert generated.reading.value == pytest.approx(550.0)
    assert recovered["value"] == pytest.approx(200.0)


def test_consecutive_injections_are_consumed_in_order_without_contamination(
    monkeypatch,
):
    simulator = DataSimulator()
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0, 4.0, 150.0)

    first = simulator.inject_anomaly(S01)
    second = simulator.inject_anomaly(S01)
    recovered_tick = simulator.next_readings(timestamp=1002.0)

    assert first.reading.value == pytest.approx(550.0)
    assert second.reading.value == pytest.approx(950.0)
    assert _reading_for(recovered_tick, "S01")["value"] == pytest.approx(200.0)
    assert all(
        item["value"] == pytest.approx(
            next(
                sensor.normal_mean
                for sensor in DataSimulator.SENSORS
                if sensor.identifier == item["sensor_id"]
            )
        )
        for item in recovered_tick
        if item["sensor_id"] != "S08"
    )


def test_tick_200_generates_automatic_s01_anomaly(monkeypatch):
    simulator = DataSimulator()
    _set_normal_values(monkeypatch)
    monkeypatch.setattr("app.engine.simulator.random.random", lambda: 0.0)

    for index in range(199):
        simulator.next_readings(timestamp=float(index))
    automatic_tick = simulator.next_readings(timestamp=199.0)

    assert _reading_for(automatic_tick, "S01")["value"] == pytest.approx(500.0)


def test_injection_requested_during_frame_applies_to_next_frame(monkeypatch):
    simulator = DataSimulator()
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)
    frame_started = threading.Event()
    injection_started = threading.Event()
    release_frame = threading.Event()

    def paused_normal_value(sensor, sensor_tick):
        if sensor.identifier == S01 and not frame_started.is_set():
            frame_started.set()
            assert release_frame.wait(timeout=2)
        return float(sensor.normal_mean)

    monkeypatch.setattr(
        simulator,
        "_generate_normal_value",
        paused_normal_value,
    )

    def request_injection():
        injection_started.set()
        return simulator.inject_anomaly(S01)

    with ThreadPoolExecutor(max_workers=2) as pool:
        frame_future = pool.submit(simulator.next_readings, 1000.0)
        assert frame_started.wait(timeout=1)
        injection_future = pool.submit(request_injection)
        assert injection_started.wait(timeout=1)
        threading.Timer(0.05, release_frame.set).start()

        first_frame = frame_future.result(timeout=2)
        generated = injection_future.result(timeout=2)

    assert _reading_for(first_frame, "S01")["value"] == pytest.approx(200.0)
    assert generated.reading.value == pytest.approx(550.0)


def test_simulator_inject_anomaly_accepts_plain_sensor_identifier(monkeypatch):
    simulator = DataSimulator()
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)

    generated = simulator.inject_anomaly("S01")

    assert generated.injection.sensor_id == S01


def test_injected_reading_payload_is_typed(monkeypatch):
    simulator = DataSimulator()
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)

    generated = simulator.inject_anomaly(S01)

    assert isinstance(generated.reading, SimulatorReading)
    assert generated.reading.sensor_id == S01
    assert generated.reading.value == pytest.approx(550.0)


def test_simulator_requires_explicit_injection_target():
    simulator = DataSimulator()

    with pytest.raises(TypeError):
        simulator.inject_anomaly()


def test_simulator_rejects_blank_identifier_as_unknown():
    simulator = DataSimulator()

    with pytest.raises(UnknownSimulatorSensorError):
        simulator.inject_anomaly("   ")


@pytest.mark.parametrize("invalid_identifier", [None, 123, object()])
def test_simulator_rejects_non_string_identifier(invalid_identifier):
    simulator = DataSimulator()

    with pytest.raises(UnknownSimulatorSensorError):
        simulator.inject_anomaly(invalid_identifier)


def test_concurrent_injections_are_generated_atomically(monkeypatch):
    simulator = DataSimulator()
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0, 4.0, 150.0)

    generated = _run_concurrently(
        lambda: simulator.inject_anomaly(S01),
        lambda: simulator.inject_anomaly(S01),
    )

    assert sorted(item.reading.value for item in generated) == pytest.approx(
        [550.0, 950.0]
    )
    assert sorted(item.injection.offset for item in generated) == pytest.approx(
        [50.0, 150.0]
    )


def test_injection_update_reaches_connected_websocket(monkeypatch):
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)
    services = create_services()
    app = create_app(services)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            live_frame = websocket.receive_json()
            response = client.post(
                "/api/analysis/inject-anomaly",
                params={"sensor_id": "S01"},
            )
            injected_update = websocket.receive_json()
            next_live_frame = websocket.receive_json()

    assert live_frame["type"] == "sensor_update"
    assert response.status_code == 200
    assert injected_update["type"] == "sensor_update"
    assert len(injected_update["sensors"]) == 1
    assert injected_update["sensors"][0]["sensor_id"] == "S01"
    assert any(
        alert["sensor_id"] == "S01" and alert["source"] == "rule"
        for alert in injected_update["alerts"]
    )
    restored = next(
        item
        for item in next_live_frame["sensors"]
        if item["sensor_id"] == "S01"
    )
    assert restored["value"] == pytest.approx(200.0)


def test_api_injection_runs_full_processing_and_is_queryable(monkeypatch):
    _set_normal_values(monkeypatch)
    _set_uniform_sequence(monkeypatch, 2.5, 50.0)
    base = 1_700_000_000.0
    services = create_services()
    services.detectors.replace_detector(
        _single_vote_arbitration_detector(
            services.engine.is_normal_reading
        )
    )
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
        recent = client.get("/api/alerts/").json()["alerts"]
        rule_alert = next(
            alert
            for alert in recent
            if alert["sensor_id"] == "S01" and alert["source"] == "rule"
        )
        matching = [
            alert
            for alert in recent
            if alert["sensor_id"] == "S01"
            and alert["timestamp"] == rule_alert["timestamp"]
        ]
        ranged = client.get(
            "/api/sensors/history/alerts",
            params={
                "start": rule_alert["timestamp"],
                "end": rule_alert["timestamp"],
            },
        ).json()["alerts"]
        detector_stats = client.get("/api/analysis/detectors").json()

    ai_alert = next(
        alert
        for alert in matching
        if alert["source"] == "ai_feature_arbitration"
    )

    assert upload.status_code == 200
    assert injection.status_code == 200
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
