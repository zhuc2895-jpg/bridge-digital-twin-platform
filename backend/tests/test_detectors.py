from app.ml.baseline import BaselineLearner
from app.ml.contracts import BaseDetector, BaselineStatus, DetectionResult
from tests.factories import reading


def detector_status(client) -> dict:
    response = client.get("/api/analysis/detectors")
    assert response.status_code == 200
    return response.json()["detectors"][0]


class AlwaysAnomalyDetector(BaseDetector):
    detector_id = "ensemble"
    display_name = "Replacement detector"

    def __init__(self):
        self.baselines = BaselineLearner()
        self.detections = 0

    def learn_baseline(self, reading, *, is_normal=True):
        return self.baselines.observe(
            reading["sensor_id"],
            reading["value"],
            is_normal=is_normal,
        )

    def get_baseline_status(self, sensor_id=None):
        if sensor_id is not None:
            return self.baselines.get_status(sensor_id)
        return self.baselines.get_statuses()

    def reset_baseline(self, sensor_id=None):
        self.baselines.reset(sensor_id)

    def detect_one(self, reading):
        self.detections += 1
        return DetectionResult(
            sensor_id=reading["sensor_id"],
            name=reading["name"],
            value=reading["value"],
            timestamp=reading["timestamp"],
            detector_id=self.detector_id,
            anomalous=True,
            score=0.9,
            confidence=0.9,
            reason="replacement detector fired",
            level="yellow",
            source="ai_dual_confirm",
            message="replacement detector fired",
        )

    def get_stats(self):
        return {
            "total_detections": self.detections,
            "ml_alerts_triggered": self.detections,
        }


class FailingDetector(BaseDetector):
    detector_id = "ensemble"
    display_name = "Failing detector"
    calls = 0

    def learn_baseline(self, reading, *, is_normal=True):
        return BaselineStatus(
            sensor_id=reading["sensor_id"],
            readings=100,
            required_readings=100,
            state="ready",
            mean=100.0,
            std=1.0,
            ema_fast=100.0,
            ema_slow=100.0,
        )

    def get_baseline_status(self, sensor_id=None):
        if sensor_id is None:
            return {}
        return BaselineStatus(
            sensor_id=sensor_id,
            readings=100,
            required_readings=100,
            state="ready",
            mean=100.0,
            std=1.0,
            ema_fast=100.0,
            ema_slow=100.0,
        )

    def reset_baseline(self, sensor_id=None):
        return None

    def detect_one(self, reading):
        self.calls += 1
        raise RuntimeError("model inference exploded")

    def get_stats(self):
        return {"total_detections": self.calls, "ml_alerts_triggered": 0}


def test_baseline_becomes_ready_after_100_normal_readings(client):
    base = 1_700_000_000.0
    records = [
        reading(value=100.0, timestamp=base + index)
        for index in range(99)
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    learning = detector_status(client)["baseline"]["sensors"]["S01"]
    assert learning["state"] == "learning"
    assert learning["readings"] == 99
    assert learning["ready"] is False

    ready_response = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=100.0, timestamp=base + 99)],
    )
    ready = detector_status(client)["baseline"]["sensors"]["S01"]

    assert ready_response.status_code == 200
    assert ready["state"] == "ready"
    assert ready["readings"] == 100
    assert ready["ready"] is True
    assert ready["mean"] == 100.0
    assert ready["std"] == 0.0
    assert ready["ema_fast"] == 100.0
    assert ready["ema_slow"] == 100.0
    assert not any(
        alert["source"].startswith("ai_")
        for alert in client.get("/api/alerts/").json()["alerts"]
    )


def test_manual_relearn_pauses_ai_until_100_new_normal_readings(client):
    base = 1_700_000_000.0
    records = [
        reading(value=100.0, timestamp=base + index)
        for index in range(100)
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    relearn = client.post(
        "/api/analysis/detectors/relearn",
        params={"sensor_id": "S01"},
    )
    status = detector_status(client)["baseline"]["sensors"]["S01"]

    assert relearn.status_code == 200
    assert relearn.json()["status"] == "relearning"
    assert status["state"] == "relearning"
    assert status["readings"] == 0
    assert status["ready"] is False

    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(value=100.0, timestamp=base + 100 + index)
            for index in range(99)
        ],
    )
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=500.0, timestamp=base + 200)],
    )
    paused = detector_status(client)["baseline"]["sensors"]["S01"]
    assert paused["state"] == "relearning"
    assert paused["readings"] == 99
    assert not any(
        alert["source"].startswith("ai_")
        for alert in client.get("/api/alerts/").json()["alerts"]
    )

    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=100.0, timestamp=base + 201)],
    )
    resumed = detector_status(client)["baseline"]["sensors"]["S01"]
    assert resumed["state"] == "ready"
    assert resumed["readings"] == 100

    resumed_alert = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=299.0, timestamp=base + 202)],
    )
    assert resumed_alert.status_code == 200
    assert any(
        alert["source"] == "ai_dual_confirm"
        for alert in client.get("/api/alerts/").json()["alerts"]
    )


def test_detector_can_be_replaced_at_the_service_seam(app, client):
    replacement = AlwaysAnomalyDetector()
    app.state.services.detectors.replace_detector(replacement)
    base = 1_700_000_000.0

    warmup = client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(value=100.0, timestamp=base + index)
            for index in range(100)
        ],
    )
    after_ready = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=100.0, timestamp=base + 100)],
    )
    stats = client.get("/api/analysis/detectors").json()
    alerts = client.get("/api/alerts/").json()["alerts"]

    assert warmup.json()["alerts_triggered"] == 0
    assert after_ready.status_code == 200
    assert any(alert["source"] == "ai_dual_confirm" for alert in alerts)
    assert stats["detector_count"] == 1
    assert stats["detectors"][0]["id"] == "ensemble"
    assert stats["detectors"][0]["name"] == "Replacement detector"


def test_detector_failure_keeps_rule_alerts_and_ingestion_available(app, client):
    app.state.services.detectors.replace_detector(FailingDetector())
    timestamp = 1_700_000_000.0

    failed_detection = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=600.0, timestamp=timestamp)],
    )
    still_ingesting = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=100.0, timestamp=timestamp + 1)],
    )
    alerts = client.get("/api/alerts/").json()["alerts"]
    detector = client.get("/api/analysis/detectors").json()["detectors"][0]

    assert failed_detection.status_code == 200
    assert failed_detection.json()["alerts_triggered"] == 1
    assert still_ingesting.status_code == 200
    assert alerts[0]["source"] == "rule"
    assert detector["health"] == "degraded"
    assert detector["failure_count"] == 2
    assert "model inference exploded" in detector["last_error"]


def test_only_physically_normal_readings_enter_the_baseline(client):
    base = 1_700_000_000.0
    abnormal = reading(value=600.0, timestamp=base)
    normal = [
        reading(value=100.0, timestamp=base + index + 1)
        for index in range(99)
    ]
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[abnormal, *normal],
    )

    baseline = detector_status(client)["baseline"]["sensors"]["S01"]

    assert baseline["state"] == "learning"
    assert baseline["readings"] == 99
    assert baseline["ready"] is False


def test_manual_global_relearn_resets_every_tracked_sensor(client):
    base = 1_700_000_000.0
    records = [
        reading(
            sensor_id=sensor_id,
            name=sensor_id,
            value=100.0,
            timestamp=base + index,
        )
        for index in range(100)
        for sensor_id in ("S01", "S02")
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    response = client.post("/api/analysis/detectors/relearn")
    sensors = detector_status(client)["baseline"]["sensors"]

    assert response.status_code == 200
    assert response.json()["sensor_id"] is None
    assert set(sensors) == {"S01", "S02"}
    assert {
        sensor["state"] for sensor in sensors.values()
    } == {"relearning"}
    assert {sensor["readings"] for sensor in sensors.values()} == {0}


def test_confirmed_anomaly_does_not_poison_a_full_detector_window(client):
    base = 1_700_000_000.0
    records = [
        reading(value=100.0 + index % 10, timestamp=base + index)
        for index in range(250)
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=600.0, timestamp=base + 250)],
    )
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=109.0, timestamp=base + 251)],
    )

    alerts = client.get("/api/alerts/").json()["alerts"]

    assert [(alert["source"], alert["value"]) for alert in alerts] == [
        ("rule", 600.0)
    ]


class ResetFailingDetector(AlwaysAnomalyDetector):
    detector_id = "reset_failure"
    display_name = "Reset failing detector"

    def __init__(self):
        super().__init__()
        self.fail_reset = True

    def reset_baseline(self, sensor_id=None):
        if self.fail_reset:
            raise RuntimeError("baseline reset unavailable")
        super().reset_baseline(sensor_id)


def test_failed_relearn_suppresses_ai_until_every_detector_resets(app, client):
    services = app.state.services
    base = 1_700_000_000.0
    services.detectors.replace_detector(AlwaysAnomalyDetector())
    reset_failure = ResetFailingDetector()
    services.detectors.register_detector(reset_failure)
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(value=100.0, timestamp=base + index)
            for index in range(100)
        ],
    )

    failed_relearn = client.post(
        "/api/analysis/detectors/relearn",
        params={"sensor_id": "S01"},
    )
    upload_while_paused = client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(value=100.0, timestamp=base + 100),
            reading(value=600.0, timestamp=base + 101),
        ],
    )
    alerts_while_paused = client.get("/api/alerts/").json()["alerts"]

    assert failed_relearn.status_code == 503
    assert upload_while_paused.status_code == 200
    assert upload_while_paused.json()["alerts_triggered"] == 1
    assert not any(
        alert["source"].startswith("ai_")
        for alert in alerts_while_paused
    )

    reset_failure.fail_reset = False
    recovered = client.post(
        "/api/analysis/detectors/relearn",
        params={"sensor_id": "S01"},
    )
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(value=100.0, timestamp=base + 102 + index)
            for index in range(101)
        ],
    )

    assert recovered.status_code == 200
    assert any(
        alert["source"].startswith("ai_")
        for alert in client.get("/api/alerts/").json()["alerts"]
    )


def test_global_relearn_failure_can_recover_one_sensor_without_unsuppressing_others(
    app,
    client,
):
    services = app.state.services
    base = 1_700_000_000.0
    services.detectors.replace_detector(AlwaysAnomalyDetector())
    reset_failure = ResetFailingDetector()
    services.detectors.register_detector(reset_failure)

    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(
                sensor_id=sensor_id,
                name=sensor_id,
                value=100.0,
                timestamp=base + index,
            )
            for index in range(100)
            for sensor_id in ("S01", "S02")
        ],
    )
    failed_global_relearn = client.post("/api/analysis/detectors/relearn")
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(sensor_id="S01", name="S01", timestamp=base + 100),
            reading(sensor_id="S02", name="S02", timestamp=base + 100),
        ],
    )

    assert failed_global_relearn.status_code == 503
    assert not any(
        alert["source"].startswith("ai_")
        for alert in client.get("/api/alerts/").json()["alerts"]
    )

    reset_failure.fail_reset = False
    recovered_s01 = client.post(
        "/api/analysis/detectors/relearn",
        params={"sensor_id": "S01"},
    )
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(
                sensor_id="S01",
                name="S01",
                timestamp=base + 101 + index,
            )
            for index in range(101)
        ],
    )
    s01_ai_alerts = [
        alert
        for alert in client.get("/api/alerts/").json()["alerts"]
        if alert["sensor_id"] == "S01"
        and alert["source"].startswith("ai_")
    ]
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(
                sensor_id="S02",
                name="S02",
                timestamp=base + 202,
            )
        ],
    )
    s02_ai_alerts = [
        alert
        for alert in client.get("/api/alerts/").json()["alerts"]
        if alert["sensor_id"] == "S02"
        and alert["source"].startswith("ai_")
    ]

    assert recovered_s01.status_code == 200
    assert s01_ai_alerts
    assert not s02_ai_alerts


def test_detector_replacement_keeps_suppression_until_new_baseline_is_ready(
    app,
    client,
):
    services = app.state.services
    base = 1_700_000_000.0
    services.detectors.replace_detector(AlwaysAnomalyDetector())
    reset_failure = ResetFailingDetector()
    services.detectors.register_detector(reset_failure)
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(value=100.0, timestamp=base + index)
            for index in range(100)
        ],
    )
    failed_relearn = client.post(
        "/api/analysis/detectors/relearn",
        params={"sensor_id": "S01"},
    )
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(value=100.0, timestamp=base + 100 + index)
            for index in range(100)
        ],
    )

    replacement = AlwaysAnomalyDetector()
    replacement.detector_id = "reset_failure"
    replacement.display_name = "Reset-capable replacement"
    services.detectors.replace_detector(replacement)
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=100.0, timestamp=base + 200)],
    )
    alerts_while_replacement_learns = client.get("/api/alerts/").json()["alerts"]

    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(value=100.0, timestamp=base + 201 + index)
            for index in range(99)
        ],
    )
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=100.0, timestamp=base + 300)],
    )

    assert failed_relearn.status_code == 503
    assert not any(
        alert["source"].startswith("ai_")
        for alert in alerts_while_replacement_learns
    )
    assert any(
        alert["source"].startswith("ai_")
        for alert in client.get("/api/alerts/").json()["alerts"]
    )
