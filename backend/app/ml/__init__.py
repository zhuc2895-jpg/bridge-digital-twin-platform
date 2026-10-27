"""Pluggable anomaly detectors and per-sensor baseline learning."""

from app.ml.baseline import BaselineLearner
from app.ml.contracts import (
    BASELINE_READING_TARGET,
    BaseDetector,
    BaselineStatus,
    DetectionResult,
)
from app.ml.registry import (
    DetectorManager,
    DetectorRegistry,
    DetectorRegistryError,
)

__all__ = [
    "BASELINE_READING_TARGET",
    "BaseDetector",
    "BaselineLearner",
    "BaselineStatus",
    "DetectionResult",
    "DetectorManager",
    "DetectorRegistry",
    "DetectorRegistryError",
]
