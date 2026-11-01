"""Cross-sensor reconstruction and spatial arbitration coverage."""

from __future__ import annotations

import numpy as np
import pytest
from app.ml.feature_arbitration import FeatureArbitrator
from app.ml.spatial_residual import SpatialResidualModel


def _snapshot(rng: np.random.Generator) -> dict[str, float]:
    independent = rng.normal(0.0, 1.0, size=6)
    s03, s04, s05, s06, s07, s08 = independent
    return {
        "S01": 2.0 * s03 + 0.5 * s04 + rng.normal(0.0, 0.01),
        "S02": 0.5 * s03 + 2.0 * s04 + rng.normal(0.0, 0.01),
        "S03": float(s03),
        "S04": float(s04),
        "S05": float(s05),
        "S06": float(s06),
        "S07": float(s07),
        "S08": float(s08),
    }


def _trained_model(
    *,
    samples: int = 120,
    min_training_snapshots: int = 120,
) -> SpatialResidualModel:
    rng = np.random.default_rng(1234)
    model = SpatialResidualModel(
        min_training_snapshots=min_training_snapshots,
        min_sensors=3,
        residual_threshold=3.0,
        min_coherent_sensors=2,
    )
    for _ in range(samples):
        model.observe_snapshot(_snapshot(rng))
    return model


def test_spatial_model_is_unavailable_until_enough_normal_snapshots() -> None:
    model = SpatialResidualModel(min_training_snapshots=30)
    rng = np.random.default_rng(1)
    for _ in range(10):
        model.observe_snapshot(_snapshot(rng))

    assert model.ready is False
    assert model.evaluate_snapshot(_snapshot(rng)) == {}
    assert model.get_stats()["required_training_snapshots"] == 30


def test_spatial_model_returns_stable_prediction_and_residual_evidence() -> None:
    model = _trained_model()
    snapshot = _snapshot(np.random.default_rng(2))

    evidence = model.evaluate_snapshot(snapshot)["S01"]

    assert model.ready is True
    assert evidence.available is True
    assert evidence.status == "consistent"
    assert evidence.predicted is not None
    assert evidence.actual == pytest.approx(snapshot["S01"])
    assert abs(evidence.standardized_residual) <= 3.0
    assert evidence.contributor_count == 7


def test_single_sensor_spike_is_isolated_and_multi_sensor_drift_is_coherent() -> None:
    model = _trained_model()
    stable = _snapshot(np.random.default_rng(3))

    isolated_snapshot = dict(stable)
    isolated_snapshot["S01"] += 30.0
    isolated = model.evaluate_snapshot(isolated_snapshot)
    assert isolated["S01"].status == "isolated_outlier"
    assert isolated["S01"].outlier_sensors == ("S01",)

    coherent_snapshot = dict(stable)
    coherent_snapshot["S01"] += 30.0
    coherent_snapshot["S02"] += 30.0
    coherent = model.evaluate_snapshot(coherent_snapshot)
    assert coherent["S01"].status == "coherent"
    assert coherent["S02"].status == "coherent"
    assert set(coherent["S01"].outlier_sensors) == {"S01", "S02"}


def test_missing_channel_degrades_without_false_spatial_outlier() -> None:
    model = _trained_model()
    snapshot = _snapshot(np.random.default_rng(4))
    snapshot.pop("S05")

    evidence = model.evaluate_snapshot(snapshot)

    assert evidence["S01"].available is True
    assert evidence["S01"].status == "consistent"
    assert evidence["S05"].status == "sensor_missing"
    assert evidence["S05"].available is False


def test_spatial_isolation_caps_time_series_confirmation_at_yellow() -> None:
    model = _trained_model()
    stable = _snapshot(np.random.default_rng(5))
    isolated_snapshot = dict(stable)
    isolated_snapshot["S01"] += 30.0
    isolated = model.evaluate_snapshot(isolated_snapshot)["S01"]
    coherent_snapshot = dict(stable)
    coherent_snapshot["S01"] += 30.0
    coherent_snapshot["S02"] += 30.0
    coherent = model.evaluate_snapshot(coherent_snapshot)["S01"]

    arbitrator = FeatureArbitrator(spatial_model=model)
    values = [0.0] * 60 + [10.0, 4.0] * 10
    isolated_decision = arbitrator._decide(
        values,
        window_available=80,
        spatial_evidence=isolated,
    )
    coherent_decision = arbitrator._decide(
        values,
        window_available=80,
        spatial_evidence=coherent,
    )

    assert isolated_decision.conclusion == "suspected"
    assert isolated_decision.level == "yellow"
    assert isolated_decision.spatial_action == "capped_isolated_outlier"
    assert isolated_decision.to_details()["spatial"]["status"] == "isolated_outlier"
    assert coherent_decision.conclusion == "confirmed"
    assert coherent_decision.level in {"orange", "red"}
    assert coherent_decision.spatial_action == "coherent_support"


def test_spatial_weights_are_configurable_and_validated() -> None:
    model = SpatialResidualModel(
        weights={"S03": 2.0, "S04": 0.5},
    )
    assert model.parameters["weights"] == {"S03": 2.0, "S04": 0.5}


def test_feature_arbitration_batch_carries_spatial_evidence() -> None:
    rng = np.random.default_rng(6789)
    arbitrator = FeatureArbitrator(
        spatial_model=SpatialResidualModel(min_training_snapshots=60)
    )
    for index in range(90):
        snapshot = _snapshot(rng)
        arbitrator.observe_many(
            [
                {
                    "sensor_id": sensor_id,
                    "name": sensor_id,
                    "type": "strain",
                    "value": value,
                    "timestamp": float(index),
                }
                for sensor_id, value in snapshot.items()
            ]
        )
    snapshot = _snapshot(rng)
    snapshot["S01"] += 30.0
    decisions = arbitrator.observe_many(
        [
            {
                "sensor_id": sensor_id,
                "name": sensor_id,
                "type": "strain",
                "value": value,
                "timestamp": 91.0,
            }
            for sensor_id, value in snapshot.items()
        ]
    )
    target = next(
        decision
        for decision, item in zip(decisions, snapshot, strict=True)
        if item == "S01"
    )

    assert target.spatial["status"] == "isolated_outlier"
    assert target.to_details()["spatial"]["sensor_id"] == "S01"
    assert target.spatial["predicted"] is not None


def test_arbitrator_trains_spatial_model_only_on_normal_readings() -> None:
    model = SpatialResidualModel(min_training_snapshots=10, min_sensors=2)
    arbitrator = FeatureArbitrator(spatial_model=model)
    readings = [
        {
            "sensor_id": "S01",
            "name": "S01",
            "type": "strain",
            "value": 1.0,
            "timestamp": 1.0,
        },
        {
            "sensor_id": "S02",
            "name": "S02",
            "type": "strain",
            "value": 2.0,
            "timestamp": 1.0,
        },
        {
            "sensor_id": "S01",
            "name": "S01",
            "type": "strain",
            "value": 5.0,
            "timestamp": 2.0,
        },
        {
            "sensor_id": "S02",
            "name": "S02",
            "type": "strain",
            "value": 6.0,
            "timestamp": 2.0,
        },
    ]

    arbitrator.observe_selected(
        readings,
        {0, 1},
        normal_predicate=lambda reading: True,
        spatial_training_indices={0, 1},
    )

    assert model.training_snapshot_count == 1
