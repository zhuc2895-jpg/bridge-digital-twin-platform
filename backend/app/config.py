"""Unified environment-backed application configuration."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.persistence import DEFAULT_CHECKPOINT_PATH
from app.threshold_provenance import (
    ThresholdProfileDocument,
    ThresholdProvenance,
    provisional_threshold_provenance,
)

_LOG_LEVELS = {
    "CRITICAL": 50,
    "ERROR": 40,
    "WARNING": 30,
    "INFO": 20,
    "DEBUG": 10,
}

_SENSOR_TYPES = ("strain", "displacement", "acceleration", "temperature")
_ALERT_LEVELS = ("yellow", "orange", "red")
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def default_thresholds() -> dict[str, dict[str, float]]:
    """Return a fresh copy of the provisional physical threshold profiles."""
    return {
        "strain": {"yellow": 300.0, "orange": 450.0, "red": 600.0},
        "displacement": {"yellow": 30.0, "orange": 50.0, "red": 80.0},
        "acceleration": {"yellow": 2.0, "orange": 3.5, "red": 5.0},
        "temperature": {"yellow": 45.0, "orange": 55.0, "red": 65.0},
    }


@dataclass(frozen=True, slots=True)
class AppConfig:
    """One validated configuration shared by application assembly and services."""

    host: str = "0.0.0.0"
    port: int = 8000
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH
    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    simulation_enabled: bool = True
    live_interval_seconds: float = 1.0
    thresholds: Mapping[str, Mapping[str, float]] = field(
        default_factory=default_thresholds
    )
    threshold_provenance: ThresholdProvenance = field(
        default_factory=provisional_threshold_provenance
    )
    ai_confidence_threshold: float = 0.7
    ai_min_votes: int = 2
    gan_submodels: int = 8
    cognition_threshold: float = 0.35
    uncertainty_threshold: float = 0.45
    feature_mean_shift_threshold: float = 2.0
    feature_variance_change_threshold: float = 2.0
    feature_trend_slope_threshold: float = 2.0
    spatial_residual_threshold: float = 3.0
    spatial_min_training_snapshots: int = 30
    spatial_min_sensors: int = 3
    spatial_min_coherent_sensors: int = 2
    spatial_alpha: float = 1e-3
    spatial_weights: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        host = self.host.strip()
        if not host:
            raise ValueError("host must be non-empty")
        if isinstance(self.port, bool) or not 1 <= int(self.port) <= 65535:
            raise ValueError("port must be between 1 and 65535")
        checkpoint_path = Path(self.checkpoint_path)
        if not str(checkpoint_path):
            raise ValueError("checkpoint_path must be non-empty")

        normalized_level = str(self.log_level).strip().upper()
        if normalized_level not in _LOG_LEVELS:
            raise ValueError(
                "log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
            )

        origins = _validate_cors_origins(self.cors_origins)
        thresholds = _validate_thresholds(self.thresholds)
        provenance = _validate_threshold_provenance(self.threshold_provenance)
        confidence = _finite_float(
            self.ai_confidence_threshold,
            "ai_confidence_threshold",
        )
        if not 0 <= confidence <= 1:
            raise ValueError("ai_confidence_threshold must be between zero and one")
        if isinstance(self.ai_min_votes, bool) or not 2 <= int(self.ai_min_votes) <= 3:
            raise ValueError("ai_min_votes must be between two and three")
        if isinstance(self.gan_submodels, bool) or int(self.gan_submodels) < 8:
            raise ValueError("gan_submodels must be at least eight")
        cognition_threshold = _finite_float(
            self.cognition_threshold,
            "cognition_threshold",
        )
        uncertainty_threshold = _finite_float(
            self.uncertainty_threshold,
            "uncertainty_threshold",
        )
        if not 0 <= cognition_threshold <= 1:
            raise ValueError("cognition_threshold must be between zero and one")
        if not 0 <= uncertainty_threshold <= 1:
            raise ValueError("uncertainty_threshold must be between zero and one")

        for field_name in (
            "feature_mean_shift_threshold",
            "feature_variance_change_threshold",
            "feature_trend_slope_threshold",
        ):
            if _finite_float(getattr(self, field_name), field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")
        interval = _finite_float(self.live_interval_seconds, "live_interval_seconds")
        if interval <= 0:
            raise ValueError("live_interval_seconds must be positive")
        spatial_threshold = _finite_float(
            self.spatial_residual_threshold,
            "spatial_residual_threshold",
        )
        if spatial_threshold <= 0:
            raise ValueError("spatial_residual_threshold must be positive")
        spatial_alpha = _finite_float(self.spatial_alpha, "spatial_alpha")
        if spatial_alpha <= 0:
            raise ValueError("spatial_alpha must be positive")
        if int(self.spatial_min_training_snapshots) < 2:
            raise ValueError("spatial_min_training_snapshots must be at least two")
        if int(self.spatial_min_sensors) < 2:
            raise ValueError("spatial_min_sensors must be at least two")
        if not 1 <= int(self.spatial_min_coherent_sensors) <= int(
            self.spatial_min_sensors
        ):
            raise ValueError("spatial_min_coherent_sensors is invalid")
        spatial_weights = _validate_spatial_weights(self.spatial_weights)

        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", int(self.port))
        object.__setattr__(self, "checkpoint_path", checkpoint_path)
        object.__setattr__(self, "log_level", normalized_level)
        object.__setattr__(self, "cors_origins", origins)
        object.__setattr__(self, "thresholds", thresholds)
        object.__setattr__(self, "threshold_provenance", provenance)
        object.__setattr__(self, "ai_confidence_threshold", confidence)
        object.__setattr__(self, "ai_min_votes", int(self.ai_min_votes))
        object.__setattr__(self, "gan_submodels", int(self.gan_submodels))
        object.__setattr__(self, "cognition_threshold", cognition_threshold)
        object.__setattr__(self, "uncertainty_threshold", uncertainty_threshold)
        object.__setattr__(self, "spatial_residual_threshold", spatial_threshold)
        object.__setattr__(self, "spatial_alpha", spatial_alpha)
        object.__setattr__(
            self,
            "spatial_min_training_snapshots",
            int(self.spatial_min_training_snapshots),
        )
        object.__setattr__(self, "spatial_min_sensors", int(self.spatial_min_sensors))
        object.__setattr__(
            self,
            "spatial_min_coherent_sensors",
            int(self.spatial_min_coherent_sensors),
        )
        object.__setattr__(self, "spatial_weights", spatial_weights)
        object.__setattr__(self, "live_interval_seconds", interval)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppConfig:
        """Build configuration from process environment values."""
        source = os.environ if environ is None else environ
        profile_path = source.get("BRIDGE_THRESHOLD_PROFILE_PATH")
        if profile_path is not None and profile_path.strip():
            conflicting_variables = [
                f"BRIDGE_{sensor_type.upper()}_{level.upper()}"
                for sensor_type in _SENSOR_TYPES
                for level in _ALERT_LEVELS
                if source.get(
                    f"BRIDGE_{sensor_type.upper()}_{level.upper()}"
                )
                is not None
            ]
            if conflicting_variables:
                raise ValueError(
                    "BRIDGE_THRESHOLD_PROFILE_PATH cannot be combined with "
                    "individual threshold overrides: "
                    + ", ".join(conflicting_variables)
                )
            profile = ThresholdProfileDocument.load(profile_path)
            thresholds = {
                sensor_type: dict(levels)
                for sensor_type, levels in profile.thresholds.items()
            }
            provenance = profile.provenance
        else:
            thresholds = default_thresholds()
            for sensor_type in _SENSOR_TYPES:
                for level in _ALERT_LEVELS:
                    variable = f"BRIDGE_{sensor_type.upper()}_{level.upper()}"
                    raw = source.get(variable)
                    if raw is not None:
                        thresholds[sensor_type][level] = _finite_float(raw, variable)
            provenance = _parse_threshold_provenance(
                source.get("BRIDGE_THRESHOLD_PROVENANCE_JSON")
            )

        origins_raw = source.get("BRIDGE_CORS_ORIGINS")
        origins = (
            _split_origins(origins_raw)
            if origins_raw is not None
            else DEFAULT_CORS_ORIGINS
        )
        checkpoint_raw = source.get("BRIDGE_CHECKPOINT_PATH")
        return cls(
            host=source.get("BRIDGE_HOST", "0.0.0.0"),
            port=_integer(source.get("BRIDGE_PORT", "8000"), "BRIDGE_PORT"),
            checkpoint_path=(
                Path(checkpoint_raw)
                if checkpoint_raw is not None
                else DEFAULT_CHECKPOINT_PATH
            ),
            log_level=source.get("BRIDGE_LOG_LEVEL", "INFO"),
            cors_origins=origins,
            simulation_enabled=_boolean(
                source.get("BRIDGE_SIMULATION_ENABLED", "true"),
                "BRIDGE_SIMULATION_ENABLED",
            ),
            live_interval_seconds=_finite_float(
                source.get("BRIDGE_LIVE_INTERVAL_SECONDS", "1.0"),
                "BRIDGE_LIVE_INTERVAL_SECONDS",
            ),
            thresholds=thresholds,
            threshold_provenance=provenance,
            ai_confidence_threshold=_finite_float(
                source.get("BRIDGE_AI_CONFIDENCE_THRESHOLD", "0.7"),
                "BRIDGE_AI_CONFIDENCE_THRESHOLD",
            ),
            ai_min_votes=_integer(
                source.get("BRIDGE_AI_MIN_VOTES", "2"),
                "BRIDGE_AI_MIN_VOTES",
            ),
            gan_submodels=_integer(
                source.get("BRIDGE_GAN_SUBMODELS", "8"),
                "BRIDGE_GAN_SUBMODELS",
            ),
            cognition_threshold=_finite_float(
                source.get("BRIDGE_COGNITION_THRESHOLD", "0.35"),
                "BRIDGE_COGNITION_THRESHOLD",
            ),
            uncertainty_threshold=_finite_float(
                source.get("BRIDGE_UNCERTAINTY_THRESHOLD", "0.45"),
                "BRIDGE_UNCERTAINTY_THRESHOLD",
            ),
            feature_mean_shift_threshold=_finite_float(
                source.get("BRIDGE_FEATURE_MEAN_SHIFT_THRESHOLD", "2.0"),
                "BRIDGE_FEATURE_MEAN_SHIFT_THRESHOLD",
            ),
            feature_variance_change_threshold=_finite_float(
                source.get("BRIDGE_FEATURE_VARIANCE_THRESHOLD", "2.0"),
                "BRIDGE_FEATURE_VARIANCE_THRESHOLD",
            ),
            feature_trend_slope_threshold=_finite_float(
                source.get("BRIDGE_FEATURE_TREND_THRESHOLD", "2.0"),
                "BRIDGE_FEATURE_TREND_THRESHOLD",
            ),
            spatial_residual_threshold=_finite_float(
                source.get("BRIDGE_SPATIAL_RESIDUAL_THRESHOLD", "3.0"),
                "BRIDGE_SPATIAL_RESIDUAL_THRESHOLD",
            ),
            spatial_min_training_snapshots=_integer(
                source.get("BRIDGE_SPATIAL_MIN_TRAINING_SNAPSHOTS", "30"),
                "BRIDGE_SPATIAL_MIN_TRAINING_SNAPSHOTS",
            ),
            spatial_min_sensors=_integer(
                source.get("BRIDGE_SPATIAL_MIN_SENSORS", "3"),
                "BRIDGE_SPATIAL_MIN_SENSORS",
            ),
            spatial_min_coherent_sensors=_integer(
                source.get("BRIDGE_SPATIAL_MIN_COHERENT_SENSORS", "2"),
                "BRIDGE_SPATIAL_MIN_COHERENT_SENSORS",
            ),
            spatial_alpha=_finite_float(
                source.get("BRIDGE_SPATIAL_ALPHA", "0.001"),
                "BRIDGE_SPATIAL_ALPHA",
            ),
            spatial_weights=_parse_spatial_weights(
                source.get("BRIDGE_SPATIAL_WEIGHTS", "{}")
            ),
        )


def _validate_cors_origins(origins: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for origin in origins:
        candidate = str(origin).strip()
        if not candidate:
            raise ValueError("CORS origins must be non-empty")
        if candidate == "*":
            raise ValueError("wildcard CORS origins are not allowed with credentials")
        if candidate not in normalized:
            normalized.append(candidate)
    if not normalized:
        raise ValueError("at least one CORS origin is required")
    return tuple(normalized)


def _split_origins(value: str) -> tuple[str, ...]:
    return _validate_cors_origins(value.split(","))


def _validate_thresholds(
    value: Mapping[str, Mapping[str, float]],
) -> dict[str, dict[str, float]]:
    if not isinstance(value, Mapping):
        raise ValueError("thresholds must be a mapping")
    result: dict[str, dict[str, float]] = {}
    for sensor_type in _SENSOR_TYPES:
        levels = value.get(sensor_type)
        if not isinstance(levels, Mapping):
            raise ValueError(f"missing threshold profile for {sensor_type}")
        profile = {
            level: _finite_float(levels.get(level), f"{sensor_type}.{level}")
            for level in _ALERT_LEVELS
        }
        if not profile["yellow"] < profile["orange"] < profile["red"]:
            raise ValueError(f"thresholds for {sensor_type} must be strictly ordered")
        if profile["yellow"] <= 0:
            raise ValueError(f"thresholds for {sensor_type} must be positive")
        result[sensor_type] = profile
    return result


def _validate_spatial_weights(
    value: Mapping[str, float] | None,
) -> dict[str, float]:
    if not value:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("spatial_weights must be a mapping")
    result: dict[str, float] = {}
    for sensor_id, weight in value.items():
        numeric = _finite_float(weight, f"spatial_weights.{sensor_id}")
        if numeric <= 0:
            raise ValueError("spatial weights must be positive")
        result[str(sensor_id)] = numeric
    return result


def _parse_spatial_weights(value: object) -> dict[str, float]:
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError("BRIDGE_SPATIAL_WEIGHTS must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("BRIDGE_SPATIAL_WEIGHTS must be a JSON object")
    return _validate_spatial_weights(decoded)


def _validate_threshold_provenance(
    value: ThresholdProvenance | Mapping[str, Any],
) -> ThresholdProvenance:
    if isinstance(value, ThresholdProvenance):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("threshold_provenance must be a mapping")
    return ThresholdProvenance.from_dict(value)


def _parse_threshold_provenance(value: object) -> ThresholdProvenance:
    if value is None or not str(value).strip():
        return provisional_threshold_provenance()
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(
            "BRIDGE_THRESHOLD_PROVENANCE_JSON must be valid JSON"
        ) from exc
    if not isinstance(decoded, dict):
        raise ValueError(
            "BRIDGE_THRESHOLD_PROVENANCE_JSON must be a JSON object"
        )
    return ThresholdProvenance.from_dict(decoded)


def _finite_float(value: object, field: str) -> float:
    if not isinstance(value, (int, float, str)):
        raise ValueError(f"{field} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _integer(value: object, field: str) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    return number


def _boolean(value: object, field: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{field} must be true or false")
