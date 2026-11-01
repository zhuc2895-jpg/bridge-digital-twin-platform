"""Multi-direction modal selection, inversion, and full-field deformation."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from app.ml.modal_inversion import (
    ModalDataset,
    ModalInversionModel,
    default_modal_dataset,
)


def _measurements_from_coordinates(
    model: ModalInversionModel,
    coordinates: dict[str, float],
    *,
    noise: float = 0.0,
    random_state: int = 42,
) -> dict[str, dict[str, float]]:
    rng = np.random.default_rng(random_state)
    selected = model.select_modes().selected_modes
    measurements: dict[str, dict[str, float]] = {}
    for sensor_id in model.dataset.sensors:
        measurements[sensor_id] = {}
        for direction in model.dataset.directions:
            value = sum(
                mode.strain_shape.get(sensor_id, {}).get(direction, 0.0)
                * coordinates[mode.mode_id]
                for mode in selected
            )
            measurements[sensor_id][direction] = value + float(
                rng.normal(0.0, noise)
            )
    return measurements


def _true_displacement(
    model: ModalInversionModel,
    coordinates: dict[str, float],
) -> dict[str, dict[str, float]]:
    selected = model.select_modes().selected_modes
    result: dict[str, dict[str, float]] = {}
    for point_id in model.dataset.field_points:
        result[point_id] = {}
        for direction in model.dataset.directions:
            result[point_id][direction] = sum(
                mode.displacement_shape.get(point_id, {}).get(direction, 0.0)
                * coordinates[mode.mode_id]
                for mode in selected
            )
    return result


def test_versioned_modal_dataset_round_trips(tmp_path) -> None:
    dataset = default_modal_dataset()
    path = tmp_path / "modes.json"
    dataset.save(path)
    loaded = ModalDataset.load(path)

    assert loaded.dataset_id == "synthetic-bridge-modes"
    assert loaded.version == "synthetic-modes-v1"
    assert len(loaded.modes) == 5
    assert loaded.metadata["source_kind"] == "synthetic"
    assert loaded.to_dict() == dataset.to_dict()


def test_energy_selection_records_truncation_and_retained_energy() -> None:
    dataset = default_modal_dataset()
    low = ModalInversionModel(dataset, target_energy=0.85)
    high = ModalInversionModel(dataset, target_energy=0.99)

    low_selection = low.select_modes()
    high_selection = high.select_modes()

    assert [mode.mode_id for mode in low_selection.selected_modes] == [
        "M1",
        "M2",
        "M3",
    ]
    assert low_selection.retained_energy == pytest.approx(0.86)
    assert low_selection.truncated_mode_ids == ("M4", "M5")
    assert len(high_selection.selected_modes) == 5


def test_synthetic_modes_recover_coordinates_residuals_and_full_field() -> None:
    model = ModalInversionModel(default_modal_dataset(), target_energy=0.85)
    selected = model.select_modes().selected_modes
    coordinates = {
        selected[0].mode_id: 1.0,
        selected[1].mode_id: -0.45,
        selected[2].mode_id: 0.25,
    }
    measurements = _measurements_from_coordinates(
        model,
        coordinates,
        noise=0.001,
        random_state=5,
    )

    result = model.invert(measurements)
    true_displacement = _true_displacement(model, coordinates)
    displacement_error = max(
        abs(
            result.displacement_field[point_id][direction]
            - true_displacement[point_id][direction]
        )
        for point_id in true_displacement
        for direction in true_displacement[point_id]
    )

    assert result.available is True
    assert result.r2 is not None and result.r2 > 0.99
    assert result.rrmse is not None and result.rrmse < 0.01
    assert displacement_error < 0.01
    assert result.modal_coordinates[selected[0].mode_id] == pytest.approx(1.0, abs=0.01)
    assert result.reliability > 0
    assert result.used_measurements == 24


def test_low_snr_and_low_confidence_directions_are_excluded() -> None:
    model = ModalInversionModel(default_modal_dataset(), target_energy=0.85)
    selected = model.select_modes().selected_modes
    coordinates = {
        selected[0].mode_id: 1.0,
        selected[1].mode_id: -0.2,
        selected[2].mode_id: 0.1,
    }
    measurements = _measurements_from_coordinates(model, coordinates)
    snr = {
        sensor_id: {"longitudinal": 0.1, "transverse": 8.0, "diagonal": 8.0}
        for sensor_id in model.dataset.sensors
    }
    confidence = {
        sensor_id: {"longitudinal": 1.0, "transverse": 1.0, "diagonal": 1.0}
        for sensor_id in model.dataset.sensors
    }
    confidence["S01"] = {
        "longitudinal": 1.0,
        "transverse": 0.0,
        "diagonal": 1.0,
    }

    result = model.invert(measurements, snr=snr, confidence=confidence)

    assert result.available is True
    assert "longitudinal" not in result.directions_used
    assert "S01:transverse:low_confidence" in result.excluded_measurements
    assert any("low_snr" in item for item in result.excluded_measurements)


def test_missing_direction_and_sensor_fault_degrade_without_crashing() -> None:
    model = ModalInversionModel(default_modal_dataset(), target_energy=0.85)
    selected = model.select_modes().selected_modes
    coordinates = {
        selected[0].mode_id: 1.0,
        selected[1].mode_id: -0.2,
        selected[2].mode_id: 0.1,
    }
    full = _measurements_from_coordinates(model, coordinates)
    longitudinal_only = {
        sensor_id: {"longitudinal": values["longitudinal"]}
        for sensor_id, values in full.items()
        if sensor_id != "S08"
    }
    confidence = {
        sensor_id: {"longitudinal": 0.0 if sensor_id == "S07" else 1.0}
        for sensor_id in longitudinal_only
    }

    result = model.invert(longitudinal_only, confidence=confidence)

    assert result.available is True
    assert result.directions_used == ("longitudinal",)
    assert "S07:longitudinal:low_confidence" in result.excluded_measurements
    assert result.used_measurements == 6


def test_insufficient_measurements_and_ill_conditioned_modes_are_reported() -> None:
    model = ModalInversionModel(default_modal_dataset(), target_energy=0.85)
    insufficient = model.invert(
        {"S01": {"longitudinal": 1.0}, "S02": {"longitudinal": 1.0}}
    )
    assert insufficient.available is False
    assert insufficient.unavailable_reason == "insufficient_measurements"

    first = default_modal_dataset().modes[0]
    duplicate = replace(
        first,
        mode_id="M_DUP",
        energy_contribution=0.4,
    )
    ill_dataset = replace(
        default_modal_dataset(),
        modes=(first, duplicate),
    )
    ill_model = ModalInversionModel(
        ill_dataset,
        target_energy=0.95,
        ridge=1e-10,
        max_condition_number=10.0,
    )
    measurements = {
        sensor_id: {
            direction: first.strain_shape[sensor_id][direction]
            for direction in ill_dataset.directions
        }
        for sensor_id in ill_dataset.sensors
    }
    ill_result = ill_model.invert(measurements)
    assert ill_result.available is True
    assert ill_result.condition_number is not None
    assert ill_result.condition_number > 10.0
    assert ill_result.reliability < 1.0


def test_api_links_explicit_measurements_and_snapshot_timestamp(client) -> None:
    model = default_modal_dataset()
    selected = ModalInversionModel(model).select_modes().selected_modes
    coordinates = {mode.mode_id: 1.0 for mode in selected}
    measurements = {
        sensor_id: {
            direction: sum(
                mode.strain_shape[sensor_id][direction] * coordinates[mode.mode_id]
                for mode in selected
            )
            for direction in model.directions
        }
        for sensor_id in model.sensors
    }

    explicit = client.post(
        "/api/analysis/deformation-inversion",
        json={"measurements": measurements},
    )
    assert explicit.status_code == 200
    assert explicit.json()["status"] == "ok"
    assert explicit.json()["source"] == "measurements"
    assert explicit.json()["displacement_field"]

    missing_history = client.post(
        "/api/analysis/deformation-inversion",
        json={"timestamp": 1.0},
    )
    assert missing_history.status_code == 400
    assert "history" in missing_history.json()["detail"]


def test_api_uses_retained_sensor_snapshot_for_time_point(client) -> None:
    from tests.factories import reading

    timestamp = 1_700_000_100.0
    records = [
        reading(
            sensor_id=f"S{index:02d}",
            value=float(index),
            timestamp=timestamp,
        )
        for index in range(1, 9)
    ]
    upload = client.post("/api/data/upload/json", json=records)
    assert upload.status_code == 200

    response = client.post(
        "/api/analysis/deformation-inversion",
        json={"timestamp": timestamp},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "snapshot"
    assert payload["timestamp"] == timestamp
    assert set(payload["snapshot"]) == {f"S{index:02d}" for index in range(1, 9)}
    assert payload["status"] == "ok"
