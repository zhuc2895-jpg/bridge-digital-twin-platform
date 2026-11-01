"""Simulation-measurement calibration contracts and compensation reliability."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from app.ml.compensation import (
    CalibrationDataset,
    DirectMeasurementModel,
    MeasurementCompensationModel,
    ResponseCompensationEstimator,
    SimulationBaseModel,
    default_calibration_dataset,
    synthetic_calibration_cases,
)


def _mean_absolute_error(
    predictions: list[float],
    targets: list[float],
) -> float:
    return float(np.mean(np.abs(np.asarray(predictions) - np.asarray(targets))))


def test_calibration_contract_round_trips_with_provenance(tmp_path: Path) -> None:
    dataset = default_calibration_dataset()
    path = tmp_path / "calibration.json"
    dataset.save(path)
    reloaded = CalibrationDataset.load(path)

    assert reloaded.dataset_id == "synthetic-bridge-calibration"
    assert reloaded.version == "synthetic-calibration-v1"
    assert len(reloaded.cases) == 200
    case = reloaded.cases[0]
    assert case.condition
    assert case.sensor_id
    assert len(case.coordinates) == 3
    assert case.direction
    assert case.features
    assert case.source in {"simulation", "measurement"}
    assert case.fidelity in {"low", "medium", "high"}
    assert case.version == reloaded.version
    assert reloaded.metadata["source_kind"] == "synthetic"
    assert {item.source for item in reloaded.cases} == {
        "simulation",
        "measurement",
    }


def test_simulation_base_model_saves_loads_and_replaces(tmp_path: Path) -> None:
    cases = synthetic_calibration_cases(120, random_state=11)
    simulation_cases = [case for case in cases if case.source == "simulation"]
    first = SimulationBaseModel()
    first.fit(simulation_cases)
    features = simulation_cases[0].features
    original = first.predict(features)

    path = tmp_path / "base.json"
    first.save(path)
    loaded = SimulationBaseModel.load(path)
    assert loaded.predict(features).prediction == pytest.approx(
        original.prediction,
        abs=1e-8,
    )

    replacement = SimulationBaseModel()
    replacement.fit(simulation_cases[:60])
    first.replace(replacement)
    assert first.predict(features).prediction == pytest.approx(
        replacement.predict(features).prediction,
        abs=1e-8,
    )


def test_compensation_reduces_holdout_error_and_is_the_default_path() -> None:
    cases = synthetic_calibration_cases(500, random_state=7)
    train = cases[:450]
    test = [case for case in cases[450:] if case.source == "measurement"]
    estimator = ResponseCompensationEstimator(train, version="test-compensation")
    estimator.fit()

    base_predictions = []
    compensated_predictions = []
    targets = []
    for case in test:
        base = estimator.base_model.predict(case.features).prediction
        compensated = estimator.compensation_model.predict(
            base,
            case.features,
        ).prediction
        base_predictions.append(base)
        compensated_predictions.append(compensated)
        targets.append(case.target)

    assert isinstance(estimator.compensation_model, MeasurementCompensationModel)
    assert _mean_absolute_error(compensated_predictions, targets) < (
        _mean_absolute_error(base_predictions, targets)
    )

    direct = DirectMeasurementModel()
    direct.fit([case for case in train if case.source == "measurement"])
    direct_prediction = direct.predict(test[0].features).prediction
    assert direct_prediction != pytest.approx(compensated_predictions[0])


def test_insufficient_training_and_missing_features_fallback_to_threshold() -> None:
    insufficient = ResponseCompensationEstimator(
        synthetic_calibration_cases(10, random_state=5),
        version="insufficient",
    )
    with pytest.raises(ValueError):
        insufficient.fit()
    fallback = insufficient.estimate(
        {
            "load_kn": 200.0,
            "temperature_c": 20.0,
            "damage_index": 0.2,
            "span_ratio": 0.5,
        }
    )
    assert fallback.prediction is None
    assert fallback.fallback == "physical_threshold"
    assert fallback.fallback_reason is not None

    cases = synthetic_calibration_cases(200, random_state=7)
    fitted = ResponseCompensationEstimator(cases, version="fitted")
    fitted.fit()
    missing = fitted.estimate(
        {
            "load_kn": 200.0,
            "damage_index": 0.2,
            "span_ratio": 0.5,
        }
    )
    assert missing.prediction is None
    assert missing.fallback_reason == "missing_required_features"
    assert missing.input_quality == pytest.approx(0.75)
    assert missing.missing_features == ("temperature_c",)


def test_out_of_domain_input_falls_back_without_claiming_prediction() -> None:
    cases = synthetic_calibration_cases(200, random_state=7)
    estimator = ResponseCompensationEstimator(cases, version="fitted")
    estimator.fit()

    estimate = estimator.estimate(
        {
            "load_kn": 10_000.0,
            "temperature_c": 300.0,
            "damage_index": 20.0,
            "span_ratio": 30.0,
        }
    )

    assert estimate.out_of_domain is True
    assert estimate.prediction is None
    assert estimate.fallback == "physical_threshold"
    assert estimate.fallback_reason == "out_of_training_domain"
    assert estimate.base_prediction is not None


def test_corrupted_model_artifact_is_rejected_and_falls_back(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text(
        '{"schema_version": 1, "feature_names": "broken"}',
        encoding="utf-8",
    )
    with pytest.raises((ValueError, KeyError, TypeError)):
        SimulationBaseModel.load(path)

    estimator = ResponseCompensationEstimator((), version="unavailable")
    fallback = estimator.estimate(
        {
            "load_kn": 200.0,
            "temperature_c": 20.0,
            "damage_index": 0.2,
            "span_ratio": 0.5,
        }
    )
    assert fallback.prediction is None
    assert fallback.fallback == "physical_threshold"


def test_response_estimate_api_returns_prediction_and_fallback(client) -> None:
    response = client.post(
        "/api/analysis/response-estimate",
        json={
            "sensor_id": "S01",
            "condition": "traffic",
            "features": {
                "load_kn": 250.0,
                "temperature_c": 20.0,
                "damage_index": 0.2,
                "span_ratio": 0.5,
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "estimated"
    assert payload["prediction"] is not None
    assert payload["fallback"] is None
    assert payload["variance"] is not None
    assert payload["reliability"] > 0
    assert payload["model_version"] == "synthetic-calibration-v1"

    fallback = client.post(
        "/api/analysis/response-estimate",
        json={
            "features": {
                "load_kn": 10_000.0,
                "temperature_c": 300.0,
                "damage_index": 20.0,
                "span_ratio": 30.0,
            }
        },
    )
    assert fallback.status_code == 200
    assert fallback.json()["status"] == "fallback"
    assert fallback.json()["fallback"] == "physical_threshold"
