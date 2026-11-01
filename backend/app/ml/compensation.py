"""Simulation-measurement compensation with explicit reliability and fallback."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

CALIBRATION_SCHEMA_VERSION = 1
DEFAULT_FEATURES = (
    "load_kn",
    "temperature_c",
    "damage_index",
    "span_ratio",
)


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    condition: str
    sensor_id: str
    coordinates: tuple[float, float, float]
    direction: str
    features: dict[str, float]
    target: float
    source: str
    fidelity: str
    version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "condition": self.condition,
            "sensor_id": self.sensor_id,
            "coordinates": list(self.coordinates),
            "direction": self.direction,
            "features": dict(self.features),
            "target": self.target,
            "source": self.source,
            "fidelity": self.fidelity,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CalibrationCase:
        coordinates = value.get("coordinates", (0.0, 0.0, 0.0))
        if not isinstance(coordinates, Sequence) or len(coordinates) != 3:
            raise ValueError("calibration coordinates must have three values")
        features = value.get("features")
        if not isinstance(features, Mapping):
            raise ValueError("calibration features must be a mapping")
        return cls(
            case_id=str(value["case_id"]),
            condition=str(value["condition"]),
            sensor_id=str(value["sensor_id"]),
            coordinates=tuple(float(item) for item in coordinates),  # type: ignore[arg-type]
            direction=str(value["direction"]),
            features={str(key): float(item) for key, item in features.items()},
            target=float(value["target"]),
            source=str(value["source"]),
            fidelity=str(value["fidelity"]),
            version=str(value["version"]),
        )


@dataclass(frozen=True)
class CalibrationDataset:
    dataset_id: str
    version: str
    cases: tuple[CalibrationCase, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = CALIBRATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "metadata": dict(self.metadata),
            "cases": [case.to_dict() for case in self.cases],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CalibrationDataset:
        if value.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
            raise ValueError("unsupported calibration schema_version")
        raw_cases = value.get("cases")
        if not isinstance(raw_cases, list):
            raise ValueError("calibration cases must be a list")
        metadata = value.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("calibration metadata must be an object")
        return cls(
            dataset_id=str(value["dataset_id"]),
            version=str(value["version"]),
            cases=tuple(CalibrationCase.from_dict(item) for item in raw_cases),
            metadata=dict(metadata),
        )

    @classmethod
    def load(cls, path: str | Path) -> CalibrationDataset:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load calibration dataset: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("calibration dataset must contain an object")
        return cls.from_dict(payload)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@dataclass(frozen=True)
class EnsemblePrediction:
    prediction: float
    variance: float
    standard_deviation: float
    domain_distance: float
    out_of_domain: bool
    submodel_predictions: tuple[float, ...]


class RidgeEnsemble:
    """Bootstrap ridge sublearners with variance and domain-distance evidence."""

    def __init__(
        self,
        feature_names: Sequence[str],
        *,
        submodels: int = 8,
        alpha: float = 1e-2,
        random_state: int = 42,
        domain_threshold: float = 3.0,
        min_samples: int = 8,
    ) -> None:
        if submodels < 2:
            raise ValueError("submodels must be at least two")
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        if domain_threshold <= 0:
            raise ValueError("domain_threshold must be positive")
        if min_samples < 2:
            raise ValueError("min_samples must be at least two")
        self.feature_names = tuple(str(name) for name in feature_names)
        if not self.feature_names:
            raise ValueError("feature_names must be non-empty")
        self.submodels = int(submodels)
        self.alpha = float(alpha)
        self.random_state = int(random_state)
        self.domain_threshold = float(domain_threshold)
        self.min_samples = int(min_samples)
        self._means: np.ndarray | None = None
        self._scales: np.ndarray | None = None
        self._covariance_inverse: np.ndarray | None = None
        self._coefficients: np.ndarray | None = None
        self._intercepts: np.ndarray | None = None
        self._training_samples = 0

    @property
    def ready(self) -> bool:
        return self._coefficients is not None

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "submodels": self.submodels,
            "alpha": self.alpha,
            "random_state": self.random_state,
            "domain_threshold": self.domain_threshold,
            "min_samples": self.min_samples,
            "training_samples": self._training_samples,
        }

    def fit(
        self,
        rows: Sequence[Mapping[str, float]],
        targets: Sequence[float],
    ) -> None:
        if len(rows) != len(targets) or len(rows) < self.min_samples:
            raise ValueError("insufficient calibration samples")
        matrix = np.asarray(
            [
                [float(row[name]) for name in self.feature_names]
                for row in rows
            ],
            dtype=float,
        )
        target_array = np.asarray(targets, dtype=float)
        if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(target_array)):
            raise ValueError("calibration values must be finite")
        means = np.mean(matrix, axis=0)
        scales = np.std(matrix, axis=0)
        scales = np.where(scales > 1e-12, scales, 1.0)
        normalized = (matrix - means) / scales
        covariance = np.cov(normalized, rowvar=False)
        covariance = np.atleast_2d(covariance) + self.alpha * np.eye(len(means))
        covariance_inverse = np.linalg.pinv(covariance)

        rng = np.random.default_rng(self.random_state)
        coefficients: list[np.ndarray] = []
        intercepts: list[float] = []
        for _ in range(self.submodels):
            indices = rng.integers(0, len(normalized), size=len(normalized))
            sample = normalized[indices]
            sample_targets = target_array[indices]
            regularized = sample.T @ sample + self.alpha * np.eye(len(means))
            try:
                coefficient = np.linalg.solve(regularized, sample.T @ sample_targets)
            except np.linalg.LinAlgError:
                coefficient = np.linalg.lstsq(sample, sample_targets, rcond=None)[0]
            intercept = float(np.mean(sample_targets - sample @ coefficient))
            coefficients.append(coefficient)
            intercepts.append(intercept)

        self._means = means
        self._scales = scales
        self._covariance_inverse = covariance_inverse
        self._coefficients = np.stack(coefficients)
        self._intercepts = np.asarray(intercepts, dtype=float)
        self._training_samples = len(rows)

    def predict(self, features: Mapping[str, float]) -> EnsemblePrediction:
        if not self.ready or self._means is None or self._scales is None:
            raise RuntimeError("ridge ensemble is not fitted")
        values = np.asarray(
            [float(features[name]) for name in self.feature_names],
            dtype=float,
        )
        if not np.all(np.isfinite(values)):
            raise ValueError("prediction features must be finite")
        normalized = (values - self._means) / self._scales
        assert self._covariance_inverse is not None
        domain_distance = float(
            math.sqrt(
                max(
                    0.0,
                    float(normalized @ self._covariance_inverse @ normalized)
                    / len(self.feature_names),
                )
            )
        )
        assert self._coefficients is not None and self._intercepts is not None
        predictions = self._coefficients @ normalized + self._intercepts
        return EnsemblePrediction(
            prediction=float(np.mean(predictions)),
            variance=float(np.var(predictions)),
            standard_deviation=float(np.std(predictions)),
            domain_distance=domain_distance,
            out_of_domain=domain_distance > self.domain_threshold,
            submodel_predictions=tuple(float(value) for value in predictions),
        )

    def save(self, path: str | Path) -> None:
        if not self.ready:
            raise ValueError("cannot save an unfitted ridge ensemble")
        assert (
            self._means is not None
            and self._scales is not None
            and self._covariance_inverse is not None
            and self._coefficients is not None
            and self._intercepts is not None
        )
        payload = {
            "schema_version": 1,
            "feature_names": list(self.feature_names),
            "submodels": self.submodels,
            "alpha": self.alpha,
            "random_state": self.random_state,
            "domain_threshold": self.domain_threshold,
            "training_samples": self._training_samples,
            "means": self._means.tolist(),
            "scales": self._scales.tolist(),
            "covariance_inverse": self._covariance_inverse.tolist(),
            "coefficients": self._coefficients.tolist(),
            "intercepts": self._intercepts.tolist(),
        }
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> RidgeEnsemble:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load ridge ensemble: {exc}") from exc
        if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
            raise ValueError("unsupported ridge ensemble artifact")
        model = cls(
            [str(name) for name in payload["feature_names"]],
            submodels=int(payload["submodels"]),
            alpha=float(payload["alpha"]),
            random_state=int(payload["random_state"]),
            domain_threshold=float(payload["domain_threshold"]),
        )
        model._means = np.asarray(payload["means"], dtype=float)
        model._scales = np.asarray(payload["scales"], dtype=float)
        model._covariance_inverse = np.asarray(
            payload["covariance_inverse"],
            dtype=float,
        )
        model._coefficients = np.asarray(payload["coefficients"], dtype=float)
        model._intercepts = np.asarray(payload["intercepts"], dtype=float)
        model._training_samples = int(payload["training_samples"])
        feature_count = len(model.feature_names)
        if (
            model._means.shape != (feature_count,)
            or model._scales.shape != (feature_count,)
            or model._covariance_inverse.shape != (feature_count, feature_count)
            or model._coefficients.shape != (model.submodels, feature_count)
            or model._intercepts.shape != (model.submodels,)
        ):
            raise ValueError("ridge ensemble artifact has inconsistent shapes")
        return model


class SimulationBaseModel:
    def __init__(self, feature_names: Sequence[str] = DEFAULT_FEATURES) -> None:
        self.ensemble = RidgeEnsemble(feature_names)

    @property
    def version(self) -> str:
        return "simulation-base-v1"

    @property
    def ready(self) -> bool:
        return self.ensemble.ready

    def fit(self, cases: Sequence[CalibrationCase]) -> None:
        self.ensemble.fit(
            [case.features for case in cases],
            [case.target for case in cases],
        )

    def predict(self, features: Mapping[str, float]) -> EnsemblePrediction:
        return self.ensemble.predict(features)

    def save(self, path: str | Path) -> None:
        self.ensemble.save(path)

    @classmethod
    def load(cls, path: str | Path) -> SimulationBaseModel:
        model = cls()
        model.ensemble = RidgeEnsemble.load(path)
        return model

    def replace(self, replacement: SimulationBaseModel) -> None:
        self.ensemble = replacement.ensemble


class MeasurementCompensationModel:
    def __init__(
        self,
        base_model: SimulationBaseModel,
        feature_names: Sequence[str] = DEFAULT_FEATURES,
    ) -> None:
        self.base_model = base_model
        self.feature_names = tuple(feature_names)
        self.ensemble = RidgeEnsemble(("base_prediction", *self.feature_names))

    @property
    def ready(self) -> bool:
        return self.ensemble.ready

    def fit(self, cases: Sequence[CalibrationCase]) -> None:
        rows = []
        targets = []
        for case in cases:
            base_prediction = self.base_model.predict(case.features).prediction
            rows.append({"base_prediction": base_prediction, **case.features})
            targets.append(case.target)
        self.ensemble.fit(rows, targets)

    def predict(
        self,
        base_prediction: float,
        features: Mapping[str, float],
    ) -> EnsemblePrediction:
        return self.ensemble.predict({"base_prediction": base_prediction, **features})


class DirectMeasurementModel:
    """Comparison-only direct mapping; not used by the default estimator."""

    def __init__(self, feature_names: Sequence[str] = DEFAULT_FEATURES) -> None:
        self.ensemble = RidgeEnsemble(feature_names)

    def fit(self, cases: Sequence[CalibrationCase]) -> None:
        self.ensemble.fit(
            [case.features for case in cases],
            [case.target for case in cases],
        )

    def predict(self, features: Mapping[str, float]) -> EnsemblePrediction:
        return self.ensemble.predict(features)


@dataclass(frozen=True)
class ResponseEstimate:
    model_version: str
    prediction: float | None
    base_prediction: float | None
    correction: float | None
    variance: float | None
    standard_deviation: float | None
    reliability: float
    out_of_domain: bool
    input_quality: float
    missing_features: tuple[str, ...]
    fallback: str | None
    fallback_reason: str | None
    domain_distance: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "prediction": self.prediction,
            "base_prediction": self.base_prediction,
            "correction": self.correction,
            "variance": self.variance,
            "standard_deviation": self.standard_deviation,
            "reliability": self.reliability,
            "out_of_domain": self.out_of_domain,
            "input_quality": self.input_quality,
            "missing_features": list(self.missing_features),
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
            "domain_distance": self.domain_distance,
        }


class ResponseCompensationEstimator:
    """Train simulation prior and measurement correction, then gate reliability."""

    def __init__(
        self,
        cases: Sequence[CalibrationCase] = (),
        *,
        version: str = "unfitted",
        min_reliability: float = 0.45,
        max_variance: float = 10_000.0,
        max_missing_features: int = 0,
    ) -> None:
        self.cases = tuple(cases)
        self.version = version
        self.min_reliability = float(min_reliability)
        self.max_variance = float(max_variance)
        self.max_missing_features = int(max_missing_features)
        self.base_model = SimulationBaseModel()
        self.compensation_model = MeasurementCompensationModel(self.base_model)
        self.available = False
        self.unavailable_reason: str | None = None
        self._fitted = False

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.base_model.ensemble.feature_names

    def fit(self, cases: Sequence[CalibrationCase] | None = None) -> None:
        selected = tuple(cases if cases is not None else self.cases)
        base_cases = [case for case in selected if case.source == "simulation"]
        measurement_cases = [case for case in selected if case.source == "measurement"]
        if len(base_cases) < 8 or len(measurement_cases) < 8:
            self.available = False
            self.unavailable_reason = "insufficient_calibration_data"
            raise ValueError("insufficient simulation or measurement calibration cases")
        self.base_model.fit(base_cases)
        self.compensation_model = MeasurementCompensationModel(self.base_model)
        self.compensation_model.fit(measurement_cases)
        self.available = True
        self.unavailable_reason = None
        self._fitted = True

    def ensure_fitted(self) -> None:
        if self._fitted:
            return
        try:
            self.fit()
        except (ValueError, RuntimeError) as exc:
            self.available = False
            self.unavailable_reason = f"{type(exc).__name__}: {exc}"

    def estimate(self, features: Mapping[str, float]) -> ResponseEstimate:
        self.ensure_fitted()
        required = self.feature_names
        missing = tuple(name for name in required if name not in features)
        quality = (len(required) - len(missing)) / len(required)
        if not self.available:
            return self._fallback(
                reason=self.unavailable_reason or "model_unavailable",
                quality=quality,
                missing=missing,
            )
        if len(missing) > self.max_missing_features:
            return self._fallback(
                reason="missing_required_features",
                quality=quality,
                missing=missing,
            )
        try:
            base = self.base_model.predict(features)
            correction = self.compensation_model.predict(base.prediction, features)
        except (KeyError, TypeError, ValueError) as exc:
            return self._fallback(
                reason=f"invalid_features: {type(exc).__name__}",
                quality=quality,
                missing=missing,
            )
        combined_domain_distance = max(
            base.domain_distance,
            correction.domain_distance,
        )
        out_of_domain = base.out_of_domain or correction.out_of_domain
        variance = correction.variance
        reliability = (
            1.0
            / (
                1.0
                + math.sqrt(max(0.0, variance))
                / max(abs(correction.prediction), 1.0)
            )
            * math.exp(-max(0.0, combined_domain_distance - 1.0))
        )
        fallback_reason = None
        if out_of_domain:
            fallback_reason = "out_of_training_domain"
        elif variance > self.max_variance:
            fallback_reason = "prediction_variance_too_high"
        elif reliability < self.min_reliability:
            fallback_reason = "reliability_below_threshold"
        return ResponseEstimate(
            model_version=self.version,
            prediction=None if fallback_reason else correction.prediction,
            base_prediction=base.prediction,
            correction=correction.prediction - base.prediction,
            variance=variance,
            standard_deviation=math.sqrt(max(0.0, variance)),
            reliability=reliability,
            out_of_domain=out_of_domain,
            input_quality=quality,
            missing_features=missing,
            fallback="physical_threshold" if fallback_reason else None,
            fallback_reason=fallback_reason,
            domain_distance=combined_domain_distance,
        )

    def _fallback(
        self,
        *,
        reason: str,
        quality: float,
        missing: tuple[str, ...],
    ) -> ResponseEstimate:
        return ResponseEstimate(
            model_version=self.version,
            prediction=None,
            base_prediction=None,
            correction=None,
            variance=None,
            standard_deviation=None,
            reliability=0.0,
            out_of_domain=False,
            input_quality=quality,
            missing_features=missing,
            fallback="physical_threshold",
            fallback_reason=reason,
            domain_distance=None,
        )


def synthetic_calibration_cases(
    count: int = 200,
    *,
    random_state: int = 42,
    version: str = "synthetic-calibration-v1",
) -> list[CalibrationCase]:
    rng = np.random.default_rng(random_state)
    cases: list[CalibrationCase] = []
    for index in range(count):
        load = float(rng.uniform(100.0, 500.0))
        temperature = float(rng.uniform(-5.0, 35.0))
        damage = float(rng.uniform(0.0, 1.0))
        span = float(rng.uniform(0.0, 1.0))
        true_response = (
            0.8 * load
            + 0.3 * temperature
            + 120.0 * damage
            + 30.0 * span
            + float(rng.normal(0.0, 1.0))
        )
        is_measurement = index >= int(count * 0.7)
        if is_measurement:
            source = "measurement"
            fidelity = "high"
            target = true_response + float(rng.normal(0.0, 0.8))
        else:
            source = "simulation"
            fidelity = "medium"
            target = (
                true_response
                + 1.0 * temperature
                - 80.0 * damage
                + float(rng.normal(0.0, 2.0))
            )
        cases.append(
            CalibrationCase(
                case_id=f"C{index:04d}",
                condition=f"condition-{index % 8}",
                sensor_id=f"S{index % 8 + 1:02d}",
                coordinates=(
                    float(index % 5) * 10.0,
                    float(index % 3) * 5.0,
                    0.0,
                ),
                direction="longitudinal",
                features={
                    "load_kn": load,
                    "temperature_c": temperature,
                    "damage_index": damage,
                    "span_ratio": span,
                },
                target=target,
                source=source,
                fidelity=fidelity,
                version=version,
            )
        )
    return cases


@lru_cache(maxsize=1)
def default_calibration_dataset() -> CalibrationDataset:
    return CalibrationDataset(
        dataset_id="synthetic-bridge-calibration",
        version="synthetic-calibration-v1",
        cases=tuple(synthetic_calibration_cases()),
        metadata={
            "source_kind": "synthetic",
            "limitations": (
                "Synthetic fixtures validate contracts and behavior only; "
                "real finite-element and field calibration accuracy is not claimed."
            ),
        },
    )
