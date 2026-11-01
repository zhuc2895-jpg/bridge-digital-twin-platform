"""Cross-sensor spatial reconstruction evidence for feature arbitration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class SpatialEvidence:
    """One sensor's spatial reconstruction result at a shared timestamp."""

    sensor_id: str
    available: bool
    status: str
    predicted: float | None
    actual: float | None
    residual: float | None
    standardized_residual: float | None
    residual_threshold: float
    outlier_sensors: tuple[str, ...]
    contributor_count: int
    model_ready: bool
    training_snapshots: int
    reason: str = ""

    def to_details(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "available": self.available,
            "status": self.status,
            "predicted": self.predicted,
            "actual": self.actual,
            "residual": self.residual,
            "standardized_residual": self.standardized_residual,
            "residual_threshold": self.residual_threshold,
            "outlier_sensors": list(self.outlier_sensors),
            "contributor_count": self.contributor_count,
            "model_ready": self.model_ready,
            "training_snapshots": self.training_snapshots,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class _TargetModel:
    target_sensor: str
    feature_sensors: tuple[str, ...]
    feature_means: np.ndarray
    feature_scales: np.ndarray
    feature_weights: np.ndarray
    coefficients: np.ndarray
    intercept: float
    residual_mean: float
    residual_scale: float
    training_samples: int

    def predict(self, snapshot: Mapping[str, float]) -> tuple[float, int]:
        features = np.zeros(len(self.feature_sensors), dtype=float)
        contributors = 0
        for index, sensor_id in enumerate(self.feature_sensors):
            if sensor_id not in snapshot:
                continue
            features[index] = (
                (snapshot[sensor_id] - self.feature_means[index])
                / self.feature_scales[index]
                * self.feature_weights[index]
            )
            contributors += 1
        return float(features @ self.coefficients + self.intercept), contributors


class SpatialResidualModel:
    """Ridge reconstruction of each sensor from the other sensors present."""

    def __init__(
        self,
        *,
        min_training_snapshots: int = 30,
        min_sensors: int = 3,
        residual_threshold: float = 3.0,
        min_coherent_sensors: int = 2,
        alpha: float = 1e-3,
        weights: Mapping[str, float] | None = None,
    ) -> None:
        if min_training_snapshots < 2:
            raise ValueError("min_training_snapshots must be at least two")
        if min_sensors < 2:
            raise ValueError("min_sensors must be at least two")
        if residual_threshold <= 0:
            raise ValueError("residual_threshold must be positive")
        if not 1 <= min_coherent_sensors <= min_sensors:
            raise ValueError("min_coherent_sensors is invalid")
        if alpha <= 0:
            raise ValueError("alpha must be positive")

        self.min_training_snapshots = int(min_training_snapshots)
        self.min_sensors = int(min_sensors)
        self.residual_threshold = float(residual_threshold)
        self.min_coherent_sensors = int(min_coherent_sensors)
        self.alpha = float(alpha)
        self.weights = {
            str(sensor_id): float(weight)
            for sensor_id, weight in (weights or {}).items()
        }
        if any(
            weight <= 0 or not math.isfinite(weight)
            for weight in self.weights.values()
        ):
            raise ValueError("spatial weights must be positive and finite")

        self._training_snapshots: list[dict[str, float]] = []
        self._pending_snapshots: dict[float, dict[str, float]] = {}
        self._finalized_timestamps: set[float] = set()
        self._models: dict[str, _TargetModel] = {}
        self._marginal_means: dict[str, float] = {}
        self._marginal_scales: dict[str, float] = {}
        self._evaluations = 0
        self._isolated_outliers = 0
        self._coherent_outliers = 0
        self._missing_sensor_evaluations = 0

    @property
    def ready(self) -> bool:
        return bool(self._models)

    @property
    def training_snapshot_count(self) -> int:
        return len(self._training_snapshots)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "min_training_snapshots": self.min_training_snapshots,
            "min_sensors": self.min_sensors,
            "residual_threshold": self.residual_threshold,
            "min_coherent_sensors": self.min_coherent_sensors,
            "alpha": self.alpha,
            "weights": dict(self.weights),
        }

    def observe_batch(self, readings: Sequence[Mapping[str, Any]]) -> None:
        """Learn from complete normal-aligned snapshots in one batch."""
        grouped: dict[float, dict[str, float]] = {}
        for reading in readings:
            try:
                timestamp = float(reading["timestamp"])
                value = float(reading["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(timestamp) or not math.isfinite(value):
                continue
            grouped.setdefault(timestamp, {})[str(reading["sensor_id"])] = value
        for snapshot in grouped.values():
            self.observe_snapshot(snapshot)

    def observe_reading(self, reading: Mapping[str, Any]) -> None:
        """Accumulate a per-reading stream until a timestamp has enough sensors."""
        try:
            timestamp = float(reading["timestamp"])
            value = float(reading["value"])
            sensor_id = str(reading["sensor_id"])
        except (KeyError, TypeError, ValueError):
            return
        if (
            timestamp in self._finalized_timestamps
            or not math.isfinite(timestamp)
            or not math.isfinite(value)
        ):
            return
        snapshot = self._pending_snapshots.setdefault(timestamp, {})
        snapshot[sensor_id] = value
        if len(snapshot) >= self.min_sensors:
            self._finalized_timestamps.add(timestamp)
            self.observe_snapshot(snapshot)
            self._pending_snapshots.pop(timestamp, None)
            if len(self._finalized_timestamps) > 2_000:
                oldest = min(self._finalized_timestamps)
                self._finalized_timestamps.discard(oldest)

    def observe_snapshot(self, snapshot: Mapping[str, float]) -> None:
        if self.ready or len(snapshot) < self.min_sensors:
            return
        clean = {
            str(sensor_id): float(value)
            for sensor_id, value in snapshot.items()
            if math.isfinite(float(value))
        }
        if len(clean) < self.min_sensors:
            return
        self._training_snapshots.append(clean)
        if len(self._training_snapshots) >= self.min_training_snapshots:
            self._fit()

    def evaluate_snapshot(
        self,
        snapshot: Mapping[str, float],
    ) -> dict[str, SpatialEvidence]:
        if not self.ready:
            return {}
        predictions: dict[str, tuple[float, float, float, int]] = {}
        for target_sensor, model in self._models.items():
            if target_sensor not in snapshot:
                continue
            predicted, contributors = model.predict(snapshot)
            if contributors < max(1, self.min_sensors - 1):
                continue
            actual = float(snapshot[target_sensor])
            residual = actual - predicted
            standardized = (
                residual - model.residual_mean
            ) / model.residual_scale
            predictions[target_sensor] = (
                predicted,
                actual,
                standardized,
                contributors,
            )

        marginal_z: dict[str, float] = {}
        for sensor_id, actual in snapshot.items():
            mean = self._marginal_means.get(sensor_id)
            scale = self._marginal_scales.get(sensor_id)
            if mean is None or scale is None:
                continue
            marginal_z[sensor_id] = (float(actual) - mean) / scale
        outlier_sensors = tuple(
            sorted(
                sensor_id
                for sensor_id, standardized in marginal_z.items()
                if abs(standardized) > self.residual_threshold
            )
        )
        evidence: dict[str, SpatialEvidence] = {}
        for target_sensor in self._models:
            self._evaluations += 1
            if target_sensor not in snapshot:
                self._missing_sensor_evaluations += 1
                evidence[target_sensor] = SpatialEvidence(
                    sensor_id=target_sensor,
                    available=False,
                    status="sensor_missing",
                    predicted=None,
                    actual=None,
                    residual=None,
                    standardized_residual=None,
                    residual_threshold=self.residual_threshold,
                    outlier_sensors=outlier_sensors,
                    contributor_count=0,
                    model_ready=True,
                    training_snapshots=len(self._training_snapshots),
                    reason="sensor has no value at this timestamp",
                )
                continue
            if target_sensor not in predictions:
                evidence[target_sensor] = SpatialEvidence(
                    sensor_id=target_sensor,
                    available=False,
                    status="insufficient_channels",
                    predicted=None,
                    actual=float(snapshot[target_sensor]),
                    residual=None,
                    standardized_residual=None,
                    residual_threshold=self.residual_threshold,
                    outlier_sensors=outlier_sensors,
                    contributor_count=0,
                    model_ready=True,
                    training_snapshots=len(self._training_snapshots),
                    reason="too few contributing sensors",
                )
                continue

            predicted, actual, standardized, contributors = predictions[target_sensor]
            marginal = marginal_z.get(target_sensor, 0.0)
            if abs(marginal) > self.residual_threshold:
                status = (
                    "coherent"
                    if len(outlier_sensors) >= self.min_coherent_sensors
                    else "isolated_outlier"
                )
                if status == "coherent":
                    self._coherent_outliers += 1
                else:
                    self._isolated_outliers += 1
            else:
                status = "consistent"
            reason = ""
            if (
                status == "consistent"
                and abs(standardized) > self.residual_threshold
            ):
                reason = "conditional residual propagated from another sensor"
            evidence[target_sensor] = SpatialEvidence(
                sensor_id=target_sensor,
                available=True,
                status=status,
                predicted=round(predicted, 9),
                actual=round(actual, 9),
                residual=round(actual - predicted, 9),
                standardized_residual=round(standardized, 6),
                residual_threshold=self.residual_threshold,
                outlier_sensors=outlier_sensors,
                contributor_count=contributors,
                model_ready=True,
                training_snapshots=len(self._training_snapshots),
                reason=reason,
            )
        return evidence

    def unavailable(self, sensor_id: str, reason: str) -> SpatialEvidence:
        return SpatialEvidence(
            sensor_id=str(sensor_id),
            available=False,
            status="unavailable",
            predicted=None,
            actual=None,
            residual=None,
            standardized_residual=None,
            residual_threshold=self.residual_threshold,
            outlier_sensors=(),
            contributor_count=0,
            model_ready=self.ready,
            training_snapshots=len(self._training_snapshots),
            reason=reason,
        )

    def reset(self) -> None:
        self._training_snapshots.clear()
        self._pending_snapshots.clear()
        self._finalized_timestamps.clear()
        self._models.clear()
        self._marginal_means.clear()
        self._marginal_scales.clear()
        self._evaluations = 0
        self._isolated_outliers = 0
        self._coherent_outliers = 0
        self._missing_sensor_evaluations = 0

    def get_stats(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "model_count": len(self._models),
            "training_snapshots": len(self._training_snapshots),
            "required_training_snapshots": self.min_training_snapshots,
            "evaluations": self._evaluations,
            "isolated_outliers": self._isolated_outliers,
            "coherent_outliers": self._coherent_outliers,
            "missing_sensor_evaluations": self._missing_sensor_evaluations,
            "parameters": self.parameters,
        }

    def _fit(self) -> None:
        sensors = sorted(
            {
                sensor_id
                for snapshot in self._training_snapshots
                for sensor_id in snapshot
            }
        )
        if len(sensors) < self.min_sensors:
            return
        models: dict[str, _TargetModel] = {}
        for target_sensor in sensors:
            feature_sensors = tuple(
                sensor_id for sensor_id in sensors if sensor_id != target_sensor
            )
            rows = [
                snapshot
                for snapshot in self._training_snapshots
                if target_sensor in snapshot
            ]
            if len(rows) < 2:
                continue
            means = np.zeros(len(feature_sensors), dtype=float)
            scales = np.ones(len(feature_sensors), dtype=float)
            weights = np.asarray(
                [self.weights.get(sensor_id, 1.0) for sensor_id in feature_sensors],
                dtype=float,
            )
            for index, sensor_id in enumerate(feature_sensors):
                values = [row[sensor_id] for row in rows if sensor_id in row]
                if values:
                    means[index] = float(np.mean(values))
                    scale = float(np.std(values))
                    scales[index] = scale if scale > 1e-12 else 1.0
            matrix = np.zeros((len(rows), len(feature_sensors)), dtype=float)
            targets = np.asarray(
                [row[target_sensor] for row in rows],
                dtype=float,
            )
            for row_index, row in enumerate(rows):
                for feature_index, sensor_id in enumerate(feature_sensors):
                    if sensor_id in row:
                        matrix[row_index, feature_index] = (
                            (row[sensor_id] - means[feature_index])
                            / scales[feature_index]
                            * weights[feature_index]
                        )
            regularized = matrix.T @ matrix + self.alpha * np.eye(
                len(feature_sensors)
            )
            try:
                coefficients = np.linalg.solve(regularized, matrix.T @ targets)
            except np.linalg.LinAlgError:
                coefficients = np.linalg.lstsq(matrix, targets, rcond=None)[0]
            intercept = float(np.mean(targets))
            residuals = targets - (matrix @ coefficients + intercept)
            residual_scale = float(np.std(residuals))
            if residual_scale <= 1e-12:
                residual_scale = max(float(np.mean(np.abs(targets))) * 1e-6, 1e-9)
            models[target_sensor] = _TargetModel(
                target_sensor=target_sensor,
                feature_sensors=feature_sensors,
                feature_means=means,
                feature_scales=scales,
                feature_weights=weights,
                coefficients=coefficients,
                intercept=intercept,
                residual_mean=float(np.mean(residuals)),
                residual_scale=residual_scale,
                training_samples=len(rows),
            )
        self._models = models
        self._marginal_means = {}
        self._marginal_scales = {}
        for sensor_id in sensors:
            values = [
                snapshot[sensor_id]
                for snapshot in self._training_snapshots
                if sensor_id in snapshot
            ]
            if not values:
                continue
            mean = float(np.mean(values))
            scale = float(np.std(values))
            self._marginal_means[sensor_id] = mean
            self._marginal_scales[sensor_id] = scale if scale > 1e-12 else 1.0
