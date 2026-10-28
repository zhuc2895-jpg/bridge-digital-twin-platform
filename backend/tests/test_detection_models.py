import math
import time

from app.ml.isolation_forest import IsolationForestDetector
from app.ml.stalwart import StalwartDetector
from tests.factories import reading


def varying_warmup(
    base: float,
    count: int = 100,
    *,
    sensor_id: str = "S01",
    name: str = "Main span strain",
    offset: int = 0,
) -> list[dict]:
    return [
        reading(
            sensor_id=sensor_id,
            name=name,
            value=float(90 + index % 21),
            timestamp=base + offset + index,
        )
        for index in range(count)
    ]


def test_stalwart_flags_a_step_but_not_steady_data():
    detector = StalwartDetector()
    base = 1_700_000_000.0
    warmup = [reading(value=100.0, timestamp=base + index) for index in range(100)]

    warmup_results = detector.detect_batch(warmup)
    steady = detector.detect_one(reading(value=100.0, timestamp=base + 100))
    step = detector.detect_one(reading(value=200.0, timestamp=base + 101))

    assert all(not result.anomalous for result in warmup_results)
    assert steady.anomalous is False
    assert steady.details["vote"] is False
    assert step.anomalous is True
    assert step.source == "ai_stalwart"
    assert step.score > 0
    assert step.confidence > 0
    assert "EMA" in step.reason
    assert step.details["vote"] is True
    assert detector.get_baseline_status("S01").ready is True

    stats = detector.get_stats()
    assert stats["parameters"]["fast_alpha"] == 0.3
    assert stats["parameters"]["slow_alpha"] == 0.05
    assert stats["parameters"]["threshold_sigma"] == 3.0
    assert stats["sensors"]["S01"]["ready"] is True


def test_stalwart_threshold_is_configurable():
    base = 1_700_000_000.0
    warmup = varying_warmup(base)
    sensitive = StalwartDetector(threshold_sigma=0.5)
    tolerant = StalwartDetector(threshold_sigma=10.0)
    sensitive.detect_batch(warmup)
    tolerant.detect_batch(warmup)

    sensitive_step = sensitive.detect_one(reading(value=200.0, timestamp=base + 100))
    tolerant_step = tolerant.detect_one(reading(value=200.0, timestamp=base + 100))

    assert sensitive_step.anomalous is True
    assert tolerant_step.anomalous is False
    assert sensitive.get_stats()["parameters"]["threshold_sigma"] == 0.5
    assert tolerant.get_stats()["parameters"]["threshold_sigma"] == 10.0


def test_isolation_forest_waits_for_enough_readings_without_training_on_candidates():
    detector = IsolationForestDetector(
        required_readings=5,
        min_readings=20,
        window_size=50,
    )
    base = 1_700_000_000.0
    detector.detect_batch(varying_warmup(base, 5))

    result = detector.detect_one(reading(value=100.0, timestamp=base + 5))
    untrusted_candidate = detector.detect_one(reading(value=1000.0, timestamp=base + 6))
    waiting_stats = detector.get_stats()["sensors"]["S01"]

    detector.detect_batch(varying_warmup(base, 15, offset=7))
    ready_stats = detector.get_stats()["sensors"]["S01"]

    assert result.reason == "baseline_learning"
    assert result.anomalous is False
    assert untrusted_candidate.anomalous is False
    assert waiting_stats["model_ready"] is False
    assert waiting_stats["training_readings"] == 5
    assert ready_stats["baseline_ready"] is True
    assert ready_stats["model_ready"] is True
    assert ready_stats["training_readings"] == 20


def test_isolation_forest_learns_a_cluster_and_flags_a_distant_outlier():
    detector = IsolationForestDetector(
        required_readings=100,
        window_size=150,
        min_readings=50,
    )
    base = 1_700_000_000.0
    warmup = varying_warmup(base)
    detector.detect_batch(warmup)

    normal = detector.detect_one(reading(value=100.0, timestamp=base + 100))
    outlier = detector.detect_one(reading(value=1000.0, timestamp=base + 101))

    assert normal.anomalous is False
    assert normal.details["vote"] is False
    assert outlier.anomalous is True
    assert outlier.source == "ai_isolation_forest"
    assert outlier.score >= 0.05
    assert outlier.details["vote"] is True
    assert "isolation score" in outlier.reason
    assert detector.get_stats()["sensors"]["S01"]["model_ready"] is True
    assert detector.get_stats()["parameters"]["window_size"] == 150


def test_isolation_forest_ready_sensor_detects_while_other_is_learning():
    detector = IsolationForestDetector(
        required_readings=10,
        window_size=50,
        min_readings=5,
    )
    base = 1_700_000_000.0
    detector.detect_batch(
        varying_warmup(base, 20, sensor_id="S01", name="Ready sensor")
    )
    detector.detect_batch(
        [
            reading(
                sensor_id="S02",
                name="Learning sensor",
                value=100.0,
                timestamp=base + index,
            )
            for index in range(5)
        ]
    )

    started = time.perf_counter()
    learning_result, ready_result = detector.detect_batch(
        [
            reading(
                sensor_id="S02",
                name="Learning sensor",
                value=100.0,
                timestamp=base + 20,
            ),
            reading(
                sensor_id="S01",
                name="Ready sensor",
                value=1000.0,
                timestamp=base + 20,
            ),
        ]
    )
    elapsed = time.perf_counter() - started
    stats = detector.get_stats()["sensors"]

    assert elapsed < 0.2
    assert learning_result.reason == "baseline_learning"
    assert learning_result.anomalous is False
    assert ready_result.anomalous is True
    assert stats["S01"]["model_ready"] is True
    assert stats["S02"]["model_ready"] is False


def test_isolation_forest_score_threshold_is_configurable():
    base = 1_700_000_000.0
    warmup = varying_warmup(base)
    sensitive = IsolationForestDetector(score_threshold=0.45)
    tolerant = IsolationForestDetector(score_threshold=0.6)
    sensitive.detect_batch(warmup)
    tolerant.detect_batch(warmup)

    sensitive_outlier = sensitive.detect_one(reading(value=120.0, timestamp=base + 100))
    tolerant_outlier = tolerant.detect_one(reading(value=120.0, timestamp=base + 100))

    assert sensitive_outlier.anomalous is True
    assert tolerant_outlier.anomalous is False
    assert sensitive.get_stats()["parameters"]["score_threshold"] == 0.45
    assert tolerant.get_stats()["parameters"]["score_threshold"] == 0.6


def test_isolation_forest_training_window_stays_bounded():
    detector = IsolationForestDetector(
        required_readings=20,
        window_size=30,
        min_readings=20,
        refit_interval=5,
    )
    base = 1_700_000_000.0
    detector.detect_batch(varying_warmup(base))

    sensor_stats = detector.get_stats()["sensors"]["S01"]

    assert sensor_stats["model_ready"] is True
    assert sensor_stats["training_readings"] == 30


def test_isolation_forest_flags_outlier_against_zero_variance_baseline():
    detector = IsolationForestDetector()
    base = 1_700_000_000.0
    detector.detect_batch(
        [reading(value=100.0, timestamp=base + index) for index in range(100)]
    )

    outlier = detector.detect_one(reading(value=1000.0, timestamp=base + 100))

    assert outlier.anomalous is True
    assert outlier.score > 0
    assert outlier.details["vote"] is True


def test_isolation_forest_keeps_sustained_in_distribution_readings_normal():
    detector = IsolationForestDetector()
    base = 1_700_000_000.0
    training_readings = [
        reading(
            value=100.0 + 5.0 * math.sin(0.3 * index),
            timestamp=base + index,
        )
        for index in range(100)
    ]
    detector.detect_batch(training_readings)

    results = [
        detector.detect_one(
            reading(
                value=100.0 + 5.0 * math.sin(0.3 * (100 + index)),
                timestamp=base + 100 + index,
            )
        )
        for index in range(200)
    ]

    anomalies = [result for result in results if result.anomalous]
    assert not anomalies, [
        (
            result.value,
            result.score,
            result.details["decision_score"],
            result.details["decision_center"],
            result.details["decision_scale"],
            result.details["value_deviation_sigma"],
        )
        for result in anomalies
    ]
