import math

import pytest

from app.ml.contracts import BaseDetector, BaselineStatus
from app.ml.feature_arbitration import FeatureArbitrationDetector, FeatureArbitrator
from app.ml.voting import VotingDetector
from tests.factories import reading


class StubModelDetector(BaseDetector):
    def __init__(self, detector_id: str, source: str, *, anomalous: bool = False) -> None:
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


def single_model_arbitration_detector() -> FeatureArbitrationDetector:
    voting = VotingDetector(
        [
            StubModelDetector("stalwart", "ai_stalwart", anomalous=True),
            StubModelDetector("gan_ae", "ai_gan_ae"),
            StubModelDetector("isolation_forest", "ai_isolation_forest"),
        ]
    )
    return FeatureArbitrationDetector(voting)


def observation(value: float, index: int = 0) -> dict:
    return reading(value=value, timestamp=1_700_000_000.0 + index)


def test_arbitrator_waits_for_the_complete_80_reading_window():
    arbitrator = FeatureArbitrator()

    decisions = [arbitrator.observe(observation(100.0, index)) for index in range(79)]
    complete = arbitrator.observe(observation(100.0, 79))

    assert all(not decision.available for decision in decisions)
    assert complete.available is True
    assert complete.window_available == 80
    assert complete.window_required == 80
    assert decisions[-1].to_details()["window"]["available"] is False
    assert complete.to_details()["window"]["available"] is True


def test_steady_window_produces_no_exceeded_features():
    history = [100.0 + (index % 5 - 2) * 0.2 for index in range(60)]
    recent = [100.0 + (index % 5 - 2) * 0.2 for index in range(20)]

    decision = FeatureArbitrator.decide_from_values(history, recent)

    assert decision.available is True
    assert decision.exceeded_features == []
    assert decision.conclusion == "normal"
    assert decision.level is None


def test_mean_drift_is_confirmed_with_multiple_features():
    history = [99.5 if index % 2 else 100.5 for index in range(60)]
    recent = [110.0 + index for index in range(20)]

    decision = FeatureArbitrator.decide_from_values(history, recent)

    assert decision.features["mean_shift"] > 2.0
    assert decision.features["variance_change"] > 2.0
    assert decision.features["trend_slope"] > 2.0
    assert len(decision.exceeded_features) >= 2
    assert decision.conclusion == "confirmed"
    assert decision.level == "red"


def test_variance_spike_is_identified_independently():
    history = [99.5 if index % 2 else 100.5 for index in range(60)]
    recent = [90.0 if index % 2 else 110.0 for index in range(20)]

    decision = FeatureArbitrator.decide_from_values(history, recent)

    assert decision.feature_evidence["variance_change"]["exceeded"] is True
    assert decision.feature_evidence["mean_shift"]["exceeded"] is False
    assert "variance_change" in decision.exceeded_features


def test_trend_change_is_identified_without_a_mean_shift():
    history = [95.0 if index % 2 else 105.0 for index in range(60)]
    recent = [90.0 + index for index in range(20)]

    decision = FeatureArbitrator.decide_from_values(history, recent)

    assert decision.feature_evidence["trend_slope"]["exceeded"] is True
    assert decision.feature_evidence["mean_shift"]["exceeded"] is False
    assert decision.feature_evidence["variance_change"]["exceeded"] is False


def test_single_feature_is_suspected_and_maps_to_yellow():
    history = [99.0 if index % 2 else 101.0 for index in range(60)]
    recent = [125.0] * 20

    decision = FeatureArbitrator.decide_from_values(history, recent)

    assert decision.exceeded_features == ["mean_shift"]
    assert decision.conclusion == "suspected"
    assert decision.level == "yellow"


def test_two_features_confirm_orange_and_three_features_confirm_red():
    history = [95.0 if index % 2 else 105.0 for index in range(60)]
    two_features = FeatureArbitrator.decide_from_values(
        history,
        [110.0 + index for index in range(20)],
    )
    three_features = FeatureArbitrator.decide_from_values(
        history,
        [90.0 + 3.0 * index for index in range(20)],
    )

    assert len(two_features.exceeded_features) == 2
    assert two_features.level == "orange"
    assert len(three_features.exceeded_features) == 3
    assert three_features.level == "red"


def test_near_zero_history_variance_stays_finite_and_tracks_direction():
    history = [100.0] * 60
    positive = FeatureArbitrator.decide_from_values(history, [102.0] * 20)
    negative = FeatureArbitrator.decide_from_values(history, [98.0] * 20)

    for decision in (positive, negative):
        assert all(math.isfinite(value) for value in decision.features.values())

    assert positive.feature_evidence["mean_shift"]["direction"] == "increase"
    assert negative.feature_evidence["mean_shift"]["direction"] == "decrease"
    assert positive.features["mean_shift"] > 0
    assert negative.features["mean_shift"] < 0
    assert positive.exceeded_features == ["mean_shift"]
    assert negative.exceeded_features == ["mean_shift"]
    assert positive.conclusion == "suspected"
    assert negative.conclusion == "suspected"
    assert positive.level == negative.level == "yellow"


def test_out_of_order_reading_uses_event_time_history():
    arbitrator = FeatureArbitrator()
    base = 1_700_000_000.0
    values = [100.0 + (index % 7 - 3) * 0.5 for index in range(100)]
    for index, value in enumerate(values):
        arbitrator.observe(
            reading(value=value, timestamp=base + index)
        )

    backfill_value = 300.0
    decision = arbitrator.observe(
        reading(value=backfill_value, timestamp=base + 80.5)
    )
    expected_values = [*values[2:81], backfill_value]
    expected = arbitrator.evaluate_values(
        expected_values[:60],
        expected_values[60:],
    )

    assert decision.features == expected.features
    assert decision.recent_mean == expected.recent_mean
    assert decision.historical_mean == expected.historical_mean


def test_shuffled_batch_is_evaluated_after_event_time_insertion():
    arbitrator = FeatureArbitrator()
    base = 1_700_000_000.0
    values = [100.0 + (index % 7 - 3) * 0.5 for index in range(100)]
    readings = [
        reading(value=value, timestamp=base + index)
        for index, value in enumerate(values)
    ]
    backfill_value = 300.0
    batch = [
        *reversed(readings),
        reading(value=backfill_value, timestamp=base + 80.5),
    ]

    decisions = arbitrator.observe_many(batch)
    expected_values = [*values[2:81], backfill_value]
    expected = arbitrator.evaluate_values(
        expected_values[:60],
        expected_values[60:],
    )

    assert decisions[0].available is True
    assert decisions[-1].features == expected.features
    assert decisions[-1].recent_mean == expected.recent_mean
    assert decisions[-1].historical_mean == expected.historical_mean


@pytest.mark.parametrize("required_features", [1, 3])
def test_confirmation_requires_exactly_two_features(required_features):
    with pytest.raises(ValueError, match="exactly two"):
        FeatureArbitrator(required_features=required_features)


def test_detector_emits_explainable_confirmed_arbitration_alert():
    detector = single_model_arbitration_detector()
    history = [95.0 if index % 2 else 105.0 for index in range(60)]
    recent_prefix = [110.0 + index for index in range(19)]

    for index, value in enumerate([*history, *recent_prefix]):
        detector.arbitrator.observe(observation(value, index))

    result = detector.detect_one(observation(129.0, 79))

    assert result.anomalous is True
    assert result.source == "ai_feature_arbitration"
    assert result.level == "orange"
    assert result.details["trigger_model"] == "stalwart"
    assert result.details["triggered_models"] == ["stalwart"]
    assert set(result.details["features"]) == {
        "mean_shift",
        "variance_change",
        "trend_slope",
    }
    assert result.details["exceeded_features"]
    assert result.details["final_conclusion"] == "confirmed"
    assert result.details["window"]["recent_size"] == 20
    assert result.details["window"]["historical_size"] == 60


def test_detector_emits_downgraded_suspected_arbitration_alert():
    detector = single_model_arbitration_detector()
    history = [99.0 if index % 2 else 101.0 for index in range(60)]
    recent_prefix = [125.0] * 19

    for index, value in enumerate([*history, *recent_prefix]):
        detector.arbitrator.observe(observation(value, index))

    result = detector.detect_one(observation(125.0, 79))

    assert result.anomalous is True
    assert result.source == "ai_feature_arbitration"
    assert result.level == "yellow"
    assert result.details["exceeded_features"] == ["mean_shift"]
    assert result.details["final_conclusion"] == "suspected"


def test_majority_confirmation_remains_higher_than_single_model_arbitration():
    single = single_model_arbitration_detector()
    history = [99.0 if index % 2 else 101.0 for index in range(60)]
    recent_prefix = [125.0] * 19
    for index, value in enumerate([*history, *recent_prefix]):
        single.arbitrator.observe(observation(value, index))
    majority = VotingDetector(
        [
            StubModelDetector("stalwart", "ai_stalwart", anomalous=True),
            StubModelDetector("gan_ae", "ai_gan_ae", anomalous=True),
            StubModelDetector("isolation_forest", "ai_isolation_forest"),
        ]
    )

    single_result = single.detect_one(observation(125.0, 79))
    majority_result = majority.detect_one(observation(125.0, 79))
    level_order = {"yellow": 0, "orange": 1, "red": 2}

    assert majority_result.source == "ai_dual_confirm"
    assert level_order[majority_result.level] >= level_order[single_result.level]


def test_feature_arbitration_alert_is_persisted_through_ingestion(client, app):
    app.state.services.detectors.replace_detector(
        single_model_arbitration_detector()
    )
    history = [99.0 if index % 2 else 101.0 for index in range(60)]
    recent_prefix = [125.0] * 19
    records = [
        observation(value, index)
        for index, value in enumerate([*history, *recent_prefix, 125.0])
    ]

    response = client.post(
        "/api/data/upload/json?push_live=false",
        json=records,
    )
    alerts = [
        alert
        for alert in client.get("/api/alerts/").json()["alerts"]
        if alert["source"] == "ai_feature_arbitration"
    ]

    assert response.status_code == 200
    assert len(alerts) == 1
    assert alerts[0]["level"] == "yellow"
    assert alerts[0]["details"]["trigger_model"] == "stalwart"
    assert alerts[0]["details"]["final_conclusion"] == "suspected"
    assert alerts[0]["details"]["exceeded_features"] == ["mean_shift"]


def test_physically_abnormal_batch_readings_are_excluded_from_window():
    detector = single_model_arbitration_detector()
    records = [
        observation(100.0, index)
        for index in range(79)
    ] + [observation(600.0, 79)]

    results = detector.detect_batch(
        records,
        normal_predicate=lambda item: item["value"] < 300.0,
    )
    sensor_stats = detector.arbitrator.get_stats()["sensors"]["S01"]

    assert results[-1].anomalous is False
    assert sensor_stats["readings"] == 79
