"""Model cognition, uncertainty gating, arbitration, and alert evidence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pytest
from app.engine.data_engine import MonitoringEngine
from app.ml.contracts import BaseDetector, BaselineStatus, DetectionResult
from app.ml.feature_arbitration import (
    ArbitrationDecision,
    FeatureArbitrationDetector,
)
from app.ml.gan_ae import GanAEDetector
from app.ml.registry import DetectorManager, DetectorRegistry
from app.ml.voting import VotingDetector
from app.processing import SensorDataProcessor
from app.sensor_batch import SensorBatch

from tests.factories import reading


class ConfiguredDetector(BaseDetector):
    def __init__(
        self,
        detector_id: str,
        source: str,
        *,
        anomalous: bool,
        confidence: float = 0.9,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.detector_id = detector_id
        self.display_name = detector_id
        self.source = source
        self.anomalous = anomalous
        self.confidence = confidence
        self.result_details = dict(details or {})
        self._status = BaselineStatus(
            sensor_id="S01",
            readings=100,
            required_readings=100,
            state="ready",
        )

    def detect_one(self, reading: Mapping[str, Any]) -> DetectionResult:
        return self.make_result(
            reading,
            anomalous=self.anomalous,
            score=self.confidence,
            confidence=self.confidence,
            reason="configured result",
            details=self.result_details,
        )

    def detect_batch(
        self,
        readings: Sequence[Mapping[str, Any]],
        *,
        normal_predicate=None,
    ) -> list[DetectionResult]:
        return [self.detect_one(item) for item in readings]

    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        return self._status

    def get_baseline_status(
        self,
        sensor_id: str | None = None,
    ) -> BaselineStatus | dict[str, BaselineStatus]:
        if sensor_id is None:
            return {"S01": self._status}
        return self._status

    def reset_baseline(self, sensor_id: str | None = None) -> None:
        return

    def get_stats(self) -> dict:
        return {
            "total_detections": 0,
            "ml_alerts_triggered": 0,
        }


def _train_gan(detector: GanAEDetector, count: int = 120) -> None:
    for index in range(count):
        detector.learn_baseline(
            reading(
                value=100.0 + 4.0 * (index % 7),
                timestamp=1_700_000_000.0 + index,
            )
        )


def test_gan_ae_returns_ensemble_variance_cognition_and_specs() -> None:
    detector = GanAEDetector(required_readings=100, n_submodels=8)
    _train_gan(detector)

    result = detector.detect_one(
        reading(value=500.0, timestamp=1_700_000_200.0)
    )

    assert result.details["model_ready"] is True
    assert result.details["submodel_count"] == 8
    assert len(result.details["submodel_errors"]) == 8
    assert len(result.details["submodel_votes"]) == 8
    assert len(result.details["submodel_specs"]) == 8
    assert result.details["ensemble_available"] is True
    assert result.details["reconstruction_error_variance"] >= 0
    assert 0 <= result.details["cognition"] <= 1
    assert 0 <= result.details["uncertainty"] <= 1
    assert result.details["cognition"] + result.details["uncertainty"] == (
        pytest.approx(1)
    )
    assert len({spec[1] for spec in result.details["submodel_specs"]}) > 1
    assert detector.parameters["n_submodels"] == 8


def test_gan_ae_submodel_ensemble_is_reproducible() -> None:
    first = GanAEDetector(required_readings=100, n_submodels=8)
    second = GanAEDetector(required_readings=100, n_submodels=8)
    _train_gan(first)
    _train_gan(second)
    candidate = reading(value=500.0, timestamp=1_700_000_200.0)

    first_result = first.detect_one(candidate)
    second_result = second.detect_one(candidate)

    assert first_result.details["submodel_specs"] == (
        second_result.details["submodel_specs"]
    )
    assert first_result.details["submodel_errors"] == (
        second_result.details["submodel_errors"]
    )
    assert first_result.details["cognition"] == second_result.details["cognition"]


def test_gan_ae_falls_back_safely_when_submodels_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector = GanAEDetector(required_readings=100, n_submodels=8)
    original = detector._train_adversarial_model
    calls = 0

    def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 4:
            raise RuntimeError("submodel training failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(detector, "_train_adversarial_model", flaky)
    _train_gan(detector)
    result = detector.detect_one(reading(value=500.0, timestamp=1_700_000_200.0))

    assert result.details["submodel_count"] == 4
    assert result.details["ensemble_available"] is False
    assert len(result.details["submodel_failures"]) == 4
    assert result.details["cognition"] == 1.0
    assert result.details["uncertainty"] == 0.0


def _voting_detector(
    votes: Sequence[tuple[bool, float, Mapping[str, Any]]],
    **policy_parameters: Any,
) -> VotingDetector:
    detectors = [
        ConfiguredDetector(
            f"model{index}",
            f"ai_{['stalwart', 'gan_ae', 'isolation_forest'][index]}",
            anomalous=anomalous,
            confidence=confidence,
            details=details,
        )
        for index, (anomalous, confidence, details) in enumerate(votes)
    ]
    return VotingDetector(detectors, **policy_parameters)


def test_low_cognition_caps_confirmed_result_at_yellow_suspected() -> None:
    detector = _voting_detector(
        [
            (True, 0.9, {"cognition": 0.1, "uncertainty": 0.9}),
            (True, 0.9, {"cognition": 0.9, "uncertainty": 0.1}),
        ]
    )

    result = detector.detect_one(reading())

    assert result.anomalous is True
    assert result.level == "yellow"
    assert result.details["uncertainty_gate"] is True
    assert result.details["gate_reasons"] == [
        "low_cognition",
        "high_uncertainty",
    ]
    assert result.details["consensus_confidence"] == pytest.approx(0.09)
    assert "疑似" in result.message


@pytest.mark.parametrize(
    ("cognition", "uncertainty", "expected_level"),
    [
        (0.35, 0.44, "orange"),
        (0.34, 0.44, "yellow"),
        (0.90, 0.45, "yellow"),
    ],
)
def test_cognition_and_uncertainty_threshold_boundaries(
    cognition: float,
    uncertainty: float,
    expected_level: str,
) -> None:
    detector = _voting_detector(
        [
            (True, 0.9, {"cognition": cognition, "uncertainty": uncertainty}),
            (True, 0.9, {"cognition": 0.9, "uncertainty": 0.1}),
        ]
    )
    result = detector.detect_one(reading())
    assert result.level == expected_level


@pytest.mark.parametrize(
    ("votes", "expected_anomalous", "expected_level"),
    [
        ([(True, 0.9, {}), (False, 0.1, {})], False, None),
        ([(True, 0.9, {}), (True, 0.9, {})], True, "orange"),
        (
            [(True, 0.9, {}), (True, 0.9, {}), (True, 0.9, {})],
            True,
            "red",
        ),
    ],
)
def test_normal_single_double_and_triple_vote_paths(
    votes,
    expected_anomalous: bool,
    expected_level: str | None,
) -> None:
    result = _voting_detector(votes).detect_one(reading())
    assert result.anomalous is expected_anomalous
    assert result.level == expected_level
    assert set(result.details["votes"]) == {
        f"model{index}" for index in range(len(votes))
    }


def test_uncertainty_gate_enters_arbitration_but_stays_yellow() -> None:
    decision = ArbitrationDecision(
        available=True,
        window_available=80,
        window_required=80,
        recent_window_size=20,
        historical_window_size=60,
        features={
            "mean_shift": 3.0,
            "variance_change": 3.0,
            "trend_slope": 3.0,
        },
        feature_evidence={},
        exceeded_features=["mean_shift", "variance_change"],
        thresholds={"mean_shift": 2.0, "variance_change": 2.0, "trend_slope": 2.0},
        required_features=2,
        conclusion="confirmed",
        level="red",
    )
    outer = FeatureArbitrationDetector(
        ConfiguredDetector("inner", "ai_stalwart", anomalous=False)
    )
    result = DetectionResult(
        sensor_id="S01",
        name="Main span strain",
        value=500.0,
        timestamp=1700000200.0,
        detector_id="ensemble",
        anomalous=True,
        confidence=0.9,
        level="yellow",
        source="ai_dual_confirm",
        details={
            "uncertainty_gate": True,
            "triggered_models": ["stalwart", "gan_ae"],
            "votes": {"stalwart": True, "gan_ae": True},
        },
    )

    arbitrated = outer._apply_arbitration(result, decision)

    assert arbitrated.anomalous is True
    assert arbitrated.level == "yellow"
    assert arbitrated.source == "ai_feature_arbitration"
    assert arbitrated.details["final_conclusion"] == "suspected"
    assert arbitrated.details["uncertainty_gate"] is True
    assert "疑似异常" in arbitrated.message


def test_alert_lifecycle_retains_uncertainty_evidence() -> None:
    engine = MonitoringEngine()
    detector = ConfiguredDetector(
        "model0",
        "ai_gan_ae",
        anomalous=True,
        details={
            "cognition": 0.1,
            "uncertainty": 0.9,
            "consensus_confidence": 0.09,
            "uncertainty_gate": True,
        },
    )
    processor = SensorDataProcessor(
        engine,
        DetectorManager(DetectorRegistry([detector])),
    )
    processor.process(SensorBatch(records=[reading()]))

    recent = engine.get_recent_alerts()[0]
    ranged = engine.get_alerts_range(0.0, 2_000_000_000.0)[0]

    assert recent["details"]["cognition"] == 0.1
    assert recent["details"]["uncertainty"] == 0.9
    assert recent["details"]["uncertainty_gate"] is True
    assert ranged["details"]["consensus_confidence"] == 0.09


def test_detector_manager_snapshot_isolates_baseline_state() -> None:
    detector = ConfiguredDetector("model0", "ai_gan_ae", anomalous=True)
    manager = DetectorManager(DetectorRegistry([detector]))
    snapshot = manager.snapshot()

    detector.anomalous = False

    restored = snapshot.registry.get("model0")
    result = restored.detect_one(reading())
    assert result.anomalous is True
