"""Multi-direction modal inversion and full-field deformation reconstruction."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import numpy as np

MODAL_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModalMode:
    mode_id: str
    frequency_hz: float
    energy_contribution: float
    strain_shape: dict[str, dict[str, float]]
    displacement_shape: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode_id": self.mode_id,
            "frequency_hz": self.frequency_hz,
            "energy_contribution": self.energy_contribution,
            "strain_shape": {
                sensor_id: dict(directions)
                for sensor_id, directions in self.strain_shape.items()
            },
            "displacement_shape": {
                point_id: dict(directions)
                for point_id, directions in self.displacement_shape.items()
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ModalMode:
        strain_shape = value.get("strain_shape")
        displacement_shape = value.get("displacement_shape")
        if not isinstance(strain_shape, Mapping) or not isinstance(
            displacement_shape,
            Mapping,
        ):
            raise ValueError("modal shapes must be mappings")
        return cls(
            mode_id=str(value["mode_id"]),
            frequency_hz=float(value["frequency_hz"]),
            energy_contribution=float(value["energy_contribution"]),
            strain_shape={
                str(sensor_id): {
                    str(direction): float(coefficient)
                    for direction, coefficient in directions.items()
                }
                for sensor_id, directions in strain_shape.items()
            },
            displacement_shape={
                str(point_id): {
                    str(direction): float(coefficient)
                    for direction, coefficient in directions.items()
                }
                for point_id, directions in displacement_shape.items()
            },
        )


@dataclass(frozen=True)
class ModalDataset:
    dataset_id: str
    version: str
    sensors: tuple[str, ...]
    directions: tuple[str, ...]
    field_points: tuple[str, ...]
    modes: tuple[ModalMode, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = MODAL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "sensors": list(self.sensors),
            "directions": list(self.directions),
            "field_points": list(self.field_points),
            "metadata": dict(self.metadata),
            "modes": [mode.to_dict() for mode in self.modes],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ModalDataset:
        if value.get("schema_version") != MODAL_SCHEMA_VERSION:
            raise ValueError("unsupported modal schema_version")
        modes = value.get("modes")
        if not isinstance(modes, list):
            raise ValueError("modal dataset modes must be a list")
        metadata = value.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("modal metadata must be an object")
        return cls(
            dataset_id=str(value["dataset_id"]),
            version=str(value["version"]),
            sensors=tuple(str(item) for item in value["sensors"]),
            directions=tuple(str(item) for item in value["directions"]),
            field_points=tuple(str(item) for item in value["field_points"]),
            modes=tuple(ModalMode.from_dict(mode) for mode in modes),
            metadata=dict(metadata),
        )

    @classmethod
    def load(cls, path: str | Path) -> ModalDataset:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load modal dataset: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("modal dataset must contain an object")
        return cls.from_dict(payload)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@dataclass(frozen=True)
class ModeSelection:
    selected_modes: tuple[ModalMode, ...]
    retained_energy: float
    total_energy: float
    target_energy: float
    truncated_mode_ids: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode_ids": [mode.mode_id for mode in self.selected_modes],
            "retained_energy": self.retained_energy,
            "total_energy": self.total_energy,
            "target_energy": self.target_energy,
            "truncated_mode_ids": list(self.truncated_mode_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ModalInversionResult:
    available: bool
    model_version: str
    mode_selection: ModeSelection
    modal_coordinates: dict[str, float]
    reconstructed_strain: dict[str, dict[str, float]]
    measured_strain: dict[str, dict[str, float]]
    residual: dict[str, dict[str, float]]
    displacement_field: dict[str, dict[str, float]]
    r2: float | None
    rrmse: float | None
    condition_number: float | None
    reliability: float
    used_measurements: int
    excluded_measurements: tuple[str, ...]
    directions_used: tuple[str, ...]
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "model_version": self.model_version,
            "mode_selection": self.mode_selection.to_dict(),
            "modal_coordinates": dict(self.modal_coordinates),
            "reconstructed_strain": {
                sensor_id: dict(directions)
                for sensor_id, directions in self.reconstructed_strain.items()
            },
            "measured_strain": {
                sensor_id: dict(directions)
                for sensor_id, directions in self.measured_strain.items()
            },
            "residual": {
                sensor_id: dict(directions)
                for sensor_id, directions in self.residual.items()
            },
            "displacement_field": {
                point_id: dict(directions)
                for point_id, directions in self.displacement_field.items()
            },
            "r2": self.r2,
            "rrmse": self.rrmse,
            "condition_number": self.condition_number,
            "reliability": self.reliability,
            "used_measurements": self.used_measurements,
            "excluded_measurements": list(self.excluded_measurements),
            "directions_used": list(self.directions_used),
            "unavailable_reason": self.unavailable_reason,
        }


class ModalInversionModel:
    def __init__(
        self,
        dataset: ModalDataset,
        *,
        target_energy: float = 0.85,
        ridge: float = 1e-6,
        min_snr: float = 2.0,
        min_direction_confidence: float = 0.1,
        max_condition_number: float = 1e6,
        max_modes: int | None = None,
    ) -> None:
        if not 0 < target_energy <= 1:
            raise ValueError("target_energy must be in (0, 1]")
        if ridge <= 0:
            raise ValueError("ridge must be positive")
        if min_snr <= 0:
            raise ValueError("min_snr must be positive")
        if not 0 <= min_direction_confidence <= 1:
            raise ValueError("min_direction_confidence must be in [0, 1]")
        if max_condition_number <= 1:
            raise ValueError("max_condition_number must be greater than one")
        if not dataset.modes:
            raise ValueError("modal dataset must contain at least one mode")
        self.dataset = dataset
        self.target_energy = float(target_energy)
        self.ridge = float(ridge)
        self.min_snr = float(min_snr)
        self.min_direction_confidence = float(min_direction_confidence)
        self.max_condition_number = float(max_condition_number)
        self.max_modes = max_modes

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset.dataset_id,
            "version": self.dataset.version,
            "target_energy": self.target_energy,
            "ridge": self.ridge,
            "min_snr": self.min_snr,
            "min_direction_confidence": self.min_direction_confidence,
            "max_condition_number": self.max_condition_number,
            "max_modes": self.max_modes,
        }

    def select_modes(self) -> ModeSelection:
        ordered = sorted(
            self.dataset.modes,
            key=lambda mode: mode.energy_contribution,
            reverse=True,
        )
        total_energy = sum(max(0.0, mode.energy_contribution) for mode in ordered)
        if total_energy <= 0:
            raise ValueError("modal energy contributions must be positive")
        selected: list[ModalMode] = []
        cumulative = 0.0
        for mode in ordered:
            if self.max_modes is not None and len(selected) >= self.max_modes:
                break
            selected.append(mode)
            cumulative += max(0.0, mode.energy_contribution)
            if cumulative / total_energy >= self.target_energy:
                break
        included = {mode.mode_id for mode in selected}
        truncated = tuple(
            mode.mode_id for mode in ordered if mode.mode_id not in included
        )
        return ModeSelection(
            selected_modes=tuple(selected),
            retained_energy=cumulative,
            total_energy=total_energy,
            target_energy=self.target_energy,
            truncated_mode_ids=truncated,
            reason=(
                "energy threshold reached"
                if not truncated
                else "remaining modes below target energy contribution"
            ),
        )

    def invert(
        self,
        measurements: Mapping[str, Mapping[str, float]],
        *,
        snr: Mapping[str, Mapping[str, float]] | None = None,
        confidence: Mapping[str, Mapping[str, float]] | None = None,
    ) -> ModalInversionResult:
        selection = self.select_modes()
        selected_modes = selection.selected_modes
        rows: list[np.ndarray] = []
        targets: list[float] = []
        weights: list[float] = []
        measured: dict[str, dict[str, float]] = {}
        excluded: list[str] = []
        directions_used: set[str] = set()

        for sensor_id, directions in measurements.items():
            if sensor_id not in self.dataset.sensors:
                excluded.append(f"{sensor_id}:unknown_sensor")
                continue
            for direction, raw_value in directions.items():
                key = f"{sensor_id}:{direction}"
                if direction not in self.dataset.directions:
                    excluded.append(f"{key}:unknown_direction")
                    continue
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    excluded.append(f"{key}:non_numeric")
                    continue
                if not math.isfinite(value):
                    excluded.append(f"{key}:non_finite")
                    continue
                measurement_confidence = _quality_value(
                    confidence,
                    sensor_id,
                    direction,
                    default=1.0,
                )
                measurement_snr = _quality_value(
                    snr,
                    sensor_id,
                    direction,
                    default=self.min_snr,
                )
                if measurement_snr < self.min_snr:
                    excluded.append(f"{key}:low_snr")
                    continue
                if measurement_confidence < self.min_direction_confidence:
                    excluded.append(f"{key}:low_confidence")
                    continue
                shape = [
                    mode.strain_shape.get(sensor_id, {}).get(direction, 0.0)
                    for mode in selected_modes
                ]
                if not any(abs(coefficient) > 1e-12 for coefficient in shape):
                    excluded.append(f"{key}:no_mode_contribution")
                    continue
                weight = measurement_confidence * min(
                    1.0,
                    measurement_snr / max(self.min_snr, 1e-9),
                )
                rows.append(np.asarray(shape, dtype=float))
                targets.append(value)
                weights.append(max(1e-6, weight))
                measured.setdefault(sensor_id, {})[direction] = value
                directions_used.add(direction)

        if len(rows) < len(selected_modes):
            return ModalInversionResult(
                available=False,
                model_version=self.dataset.version,
                mode_selection=selection,
                modal_coordinates={},
                reconstructed_strain={},
                measured_strain=measured,
                residual={},
                displacement_field={},
                r2=None,
                rrmse=None,
                condition_number=None,
                reliability=0.0,
                used_measurements=len(rows),
                excluded_measurements=tuple(excluded),
                directions_used=tuple(sorted(directions_used)),
                unavailable_reason="insufficient_measurements",
            )

        phi = np.vstack(rows)
        y = np.asarray(targets, dtype=float)
        weight_array = np.asarray(weights, dtype=float)
        weighted_phi = phi * np.sqrt(weight_array)[:, None]
        condition_number = float(np.linalg.cond(weighted_phi))
        normal = phi.T @ (weight_array[:, None] * phi) + self.ridge * np.eye(
            phi.shape[1]
        )
        try:
            coordinates = np.linalg.solve(normal, phi.T @ (weight_array * y))
        except np.linalg.LinAlgError:
            coordinates = np.linalg.lstsq(
                np.sqrt(weight_array)[:, None] * phi,
                np.sqrt(weight_array) * y,
                rcond=None,
            )[0]
        coordinates = np.nan_to_num(coordinates, nan=0.0, posinf=0.0, neginf=0.0)

        reconstructed: dict[str, dict[str, float]] = {}
        residual: dict[str, dict[str, float]] = {}
        row_index = 0
        for sensor_id, directions in measured.items():
            for direction, value in directions.items():
                reconstructed_value = float(phi[row_index] @ coordinates)
                reconstructed.setdefault(sensor_id, {})[direction] = round(
                    reconstructed_value,
                    9,
                )
                residual.setdefault(sensor_id, {})[direction] = round(
                    value - reconstructed_value,
                    9,
                )
                row_index += 1

        prediction = phi @ coordinates
        residual_array = y - prediction
        total_variance = float(np.sum((y - np.mean(y)) ** 2))
        residual_variance = float(np.sum(residual_array**2))
        r2 = (
            1.0 - residual_variance / total_variance
            if total_variance > 1e-12
            else 0.0
        )
        y_norm = float(np.linalg.norm(y))
        rrmse = (
            float(np.linalg.norm(residual_array) / y_norm)
            if y_norm > 1e-12
            else 0.0
        )

        displacement_field: dict[str, dict[str, float]] = {}
        for point_id in self.dataset.field_points:
            for direction in self.dataset.directions:
                value = sum(
                    mode.displacement_shape.get(point_id, {}).get(direction, 0.0)
                    * float(coordinates[index])
                    for index, mode in enumerate(selected_modes)
                )
                displacement_field.setdefault(point_id, {})[direction] = round(
                    float(value),
                    9,
                )

        energy_coverage = selection.retained_energy / selection.total_energy
        measurement_support = min(
            1.0,
            len(rows)
            / max(1, len(selected_modes) * len(self.dataset.directions)),
        )
        conditioning = 1.0 / (
            1.0
            + max(
                0.0,
                math.log10(max(condition_number, 1.0))
                - math.log10(max(self.max_condition_number, 1.0) / 100.0),
            )
        )
        reliability = max(
            0.0,
            min(1.0, energy_coverage * measurement_support * conditioning),
        )
        return ModalInversionResult(
            available=True,
            model_version=self.dataset.version,
            mode_selection=selection,
            modal_coordinates={
                mode.mode_id: round(float(coordinates[index]), 9)
                for index, mode in enumerate(selected_modes)
            },
            reconstructed_strain=reconstructed,
            measured_strain=measured,
            residual=residual,
            displacement_field=displacement_field,
            r2=round(float(r2), 9),
            rrmse=round(float(rrmse), 9),
            condition_number=round(condition_number, 6),
            reliability=round(reliability, 6),
            used_measurements=len(rows),
            excluded_measurements=tuple(excluded),
            directions_used=tuple(sorted(directions_used)),
        )


def _quality_value(
    values: Mapping[str, Mapping[str, float]] | None,
    sensor_id: str,
    direction: str,
    *,
    default: float,
) -> float:
    if values is None:
        return default
    sensor_values = values.get(sensor_id)
    if not isinstance(sensor_values, Mapping):
        return default
    try:
        return float(sensor_values.get(direction, default))
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=1)
def default_modal_dataset() -> ModalDataset:
    sensors = tuple(f"S{index:02d}" for index in range(1, 9))
    directions = ("longitudinal", "transverse", "diagonal")
    field_points = tuple(f"P{index:02d}" for index in range(12))
    energy = (0.50, 0.24, 0.12, 0.09, 0.05)
    rng = np.random.default_rng(12345)
    strain_basis, _ = np.linalg.qr(
        rng.normal(size=(len(sensors) * len(directions), len(energy)))
    )
    displacement_basis, _ = np.linalg.qr(
        rng.normal(size=(len(field_points) * len(directions), len(energy)))
    )
    modes = []
    for mode_index, contribution in enumerate(energy, start=1):
        strain_shape: dict[str, dict[str, float]] = {}
        strain_column = mode_index - 1
        for sensor_index, sensor_id in enumerate(sensors, start=1):
            strain_shape[sensor_id] = {}
            for direction_index, direction in enumerate(directions):
                row = (sensor_index - 1) * len(directions) + direction_index
                strain_shape[sensor_id][direction] = round(
                    float(strain_basis[row, strain_column]),
                    6,
                )
        displacement_shape: dict[str, dict[str, float]] = {}
        for point_index, point_id in enumerate(field_points, start=1):
            displacement_shape[point_id] = {}
            for direction_index, direction in enumerate(directions):
                row = (point_index - 1) * len(directions) + direction_index
                displacement_shape[point_id][direction] = round(
                    float(displacement_basis[row, strain_column]),
                    6,
                )
        modes.append(
            ModalMode(
                mode_id=f"M{mode_index}",
                frequency_hz=round(1.2 + mode_index * 0.8, 3),
                energy_contribution=contribution,
                strain_shape=strain_shape,
                displacement_shape=displacement_shape,
            )
        )
    return ModalDataset(
        dataset_id="synthetic-bridge-modes",
        version="synthetic-modes-v1",
        sensors=sensors,
        directions=directions,
        field_points=field_points,
        modes=tuple(modes),
        metadata={
            "source_kind": "synthetic",
            "limitations": (
                "Synthetic modes validate inversion behavior only. Real accuracy "
                "requires finite-element modes and measured deformation."
            ),
        },
    )
