import math
import time

from app.ml.contracts import BaseDetector, BaselineStatus
from app.ml.gan_ae import GanAEDetector
from app.ml.voting import VotingDetector
from tests.factories import reading


class StubDetector(BaseDetector):
    def __init__(
        self,
        detector_id: str,
        source: str,
        *,
        ready: bool = True,
        anomalous: bool = False,
        confidence: float = 0.9,
        score: float = 0.8,
    ) -> None:
        self.detector_id = detector_id
        self.display_name = detector_id
        self.source = source
        self.ready = ready
        self.anomalous = anomalous
        self.confidence = confidence
        self.score = score

    def learn_baseline(self, reading, *, is_normal=True):
        return self.get_baseline_status(reading["sensor_id"])

    def get_baseline_status(self, sensor_id=None):
        status = BaselineStatus(
            sensor_id=sensor_id or "S01",
            readings=1 if self.ready else 0,
            required_readings=1,
            state="ready" if self.ready else "learning",
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
            score=self.score,
            confidence=self.confidence,
            reason="stub anomaly" if self.anomalous else "stub normal",
            details={
                "vote": self.anomalous,
                "model_ready": self.ready,
            },
        )

    def get_stats(self):
        return {
            "total_detections": 0,
            "ml_alerts_triggered": 0,
            "parameters": {"ready": self.ready},
        }


def model(
    detector_id: str,
    source: str,
    *,
    ready: bool = True,
    anomalous: bool = False,
    confidence: float = 0.9,
    score: float = 0.8,
) -> StubDetector:
    return StubDetector(
        detector_id,
        source,
        ready=ready,
        anomalous=anomalous,
        confidence=confidence,
        score=score,
    )


def voting_with(
    *,
    stalwart: StubDetector | None = None,
    gan_ae: StubDetector | None = None,
    isolation_forest: StubDetector | None = None,
) -> VotingDetector:
    return VotingDetector(
        [
            stalwart or model("stalwart", "ai_stalwart"),
            gan_ae or model("gan_ae", "ai_gan_ae"),
            isolation_forest or model("isolation_forest", "ai_isolation_forest"),
        ]
    )


def test_gan_ae_learns_reconstruction_distribution_and_flags_step():
    detector = GanAEDetector(required_readings=100, sequence_length=8)
    base = 1_700_000_000.0
    warmup = [
        reading(
            value=100.0 + 4.0 * math.sin(0.2 * index),
            timestamp=base + index,
        )
        for index in range(100)
    ]

    warmup_results = detector.detect_batch(warmup)
    steady = detector.detect_one(
        reading(
            value=100.0 + 4.0 * math.sin(0.2 * 100),
            timestamp=base + 100,
        )
    )
    step = detector.detect_one(reading(value=250.0, timestamp=base + 101))

    assert all(not result.anomalous for result in warmup_results)
    assert steady.anomalous is False
    assert step.anomalous is True
    assert step.source == "ai_gan_ae"
    assert step.details["vote"] is True
    assert step.details["reconstruction_error"] > step.details["threshold"]
    assert step.confidence >= 0.7
    assert step.details["gan_enabled"] is True
    assert step.details["adversarial_steps"] == 25
    assert 0.0 <= step.details["discriminator_real_probability"] <= 1.0
    assert detector.get_baseline_status("S01").ready is True
    assert detector.get_stats()["sensors"]["S01"]["model_ready"] is True


def test_voting_requires_two_confident_votes_and_records_participants():
    detector = voting_with(stalwart=model("stalwart", "ai_stalwart", anomalous=True))

    result = detector.detect_one(reading(value=200.0))

    assert result.anomalous is False
    assert result.details["vote_count"] == 1
    assert result.details["votes"]["stalwart"] is True


def test_voting_two_votes_emits_dual_confirmation_with_diagnostics():
    detector = voting_with(
        stalwart=model("stalwart", "ai_stalwart", anomalous=True, confidence=0.82),
        gan_ae=model("gan_ae", "ai_gan_ae", anomalous=True, confidence=0.91),
    )

    result = detector.detect_one(reading(value=200.0))

    assert result.anomalous is True
    assert result.source == "ai_dual_confirm"
    assert result.level == "orange"
    assert result.confidence == 0.91
    assert result.details["vote_count"] == 2
    assert result.details["participating_models"] == ["stalwart", "gan_ae"]
    assert result.details["model_results"]["stalwart"]["source"] == "ai_stalwart"
    assert result.details["model_results"]["gan_ae"]["confidence"] == 0.91


def test_voting_three_votes_emit_red_confirmation():
    detector = voting_with(
        stalwart=model("stalwart", "ai_stalwart", anomalous=True),
        gan_ae=model("gan_ae", "ai_gan_ae", anomalous=True),
        isolation_forest=model(
            "isolation_forest",
            "ai_isolation_forest",
            anomalous=True,
        ),
    )

    result = detector.detect_one(reading(value=200.0))

    assert result.anomalous is True
    assert result.level == "red"
    assert result.details["vote_count"] == 3
    assert result.details["participating_models"] == [
        "stalwart",
        "gan_ae",
        "isolation_forest",
    ]


def test_low_confidence_vote_does_not_count_toward_majority():
    detector = voting_with(
        stalwart=model(
            "stalwart",
            "ai_stalwart",
            anomalous=True,
            confidence=0.69,
        ),
        gan_ae=model("gan_ae", "ai_gan_ae", anomalous=True, confidence=0.9),
    )

    result = detector.detect_one(reading(value=200.0))

    assert result.anomalous is False
    assert result.details["vote_count"] == 1
    assert result.details["votes"]["stalwart"] is False
    assert result.details["model_results"]["stalwart"]["confidence"] == 0.69


def test_unready_models_do_not_vote_or_emit_alerts():
    detector = voting_with(
        stalwart=model("stalwart", "ai_stalwart", ready=False, anomalous=True),
        gan_ae=model("gan_ae", "ai_gan_ae", ready=False, anomalous=True),
        isolation_forest=model(
            "isolation_forest",
            "ai_isolation_forest",
            ready=False,
            anomalous=True,
        ),
    )

    result = detector.detect_batch([reading(value=900.0)])[0]

    assert result.anomalous is False
    assert result.details["vote_count"] == 0
    assert result.details["model_ready"] is False
    assert all(not vote for vote in result.details["votes"].values())


def test_normal_steady_data_stays_normal_after_baseline():
    detector = VotingDetector()
    base = 1_700_000_000.0
    detector.detect_batch(
        [reading(value=100.0, timestamp=base + index) for index in range(100)]
    )

    results = [
        detector.detect_one(reading(value=100.0, timestamp=base + 100 + index))
        for index in range(100)
    ]

    assert all(not result.anomalous for result in results)


def test_three_model_inference_stays_below_200ms():
    detector = VotingDetector()
    base = 1_700_000_000.0
    detector.detect_batch(
        [
            reading(
                value=100.0 + 3.0 * math.sin(0.2 * index),
                timestamp=base + index,
            )
            for index in range(100)
        ]
    )

    started = time.perf_counter()
    result = detector.detect_one(reading(value=250.0, timestamp=base + 100))
    elapsed = time.perf_counter() - started

    assert result.details["inference_elapsed_ms"] < 200
    assert elapsed < 0.2


def test_ai_alert_details_are_retained(client):
    base = 1_700_000_000.0
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(
                value=100.0 + 3.0 * math.sin(0.2 * index),
                timestamp=base + index,
            )
            for index in range(100)
        ],
    )
    response = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=250.0, timestamp=base + 100)],
    )

    ai_alerts = [
        alert
        for alert in client.get("/api/alerts/").json()["alerts"]
        if alert["source"].startswith("ai_")
    ]

    assert response.status_code == 200
    assert ai_alerts
    assert ai_alerts[0]["source"] == "ai_dual_confirm"
    assert len(ai_alerts[0]["details"]["participating_models"]) >= 2
    assert ai_alerts[0]["details"]["model_results"]


def test_normal_steady_data_after_baseline_does_not_generate_ai_alerts(client):
    base = 1_700_000_000.0
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=100.0, timestamp=base + index) for index in range(300)],
    )

    alerts = client.get("/api/alerts/").json()["alerts"]

    assert not any(alert["source"].startswith("ai_") for alert in alerts)


def test_detector_status_exposes_three_voting_models(client):
    base = 1_700_000_000.0
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=100.0, timestamp=base + index) for index in range(100)],
    )

    detector = client.get("/api/analysis/detectors").json()["detectors"][0]
    models = detector["stats"]["models"]

    assert {model["id"] for model in models} == {
        "stalwart",
        "gan_ae",
        "isolation_forest",
    }
    assert all(model["sensors"]["S01"]["ready"] for model in models)


def test_steady_shortcut_does_not_hide_sustained_anomalies():
    detector = VotingDetector()
    base = 1_700_000_000.0
    detector.detect_batch(
        [reading(value=100.0, timestamp=base + index) for index in range(100)]
    )

    results = detector.detect_batch(
        [reading(value=900.0, timestamp=base + 100 + index) for index in range(110)]
    )

    assert all(result.anomalous for result in results)


def test_voting_gates_are_fixed_by_specification():
    for threshold in (0.69, 0.8):
        try:
            VotingDetector(confidence_threshold=threshold)
        except ValueError as exc:
            assert "0.7" in str(exc)
        else:
            raise AssertionError("confidence threshold must be fixed at 0.7")

    for vote_count in (1, 3):
        try:
            VotingDetector(min_votes=vote_count)
        except ValueError as exc:
            assert "two" in str(exc)
        else:
            raise AssertionError("min_votes must be fixed at two")
