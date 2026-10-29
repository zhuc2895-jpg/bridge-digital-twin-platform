"""Pluggable anomaly detectors and per-sensor baseline learning."""

from app.ml.baseline import BaselineLearner
from app.ml.contracts import (
    BASELINE_READING_TARGET,
    BaseDetector,
    BaselineStatus,
    DetectionResult,
)
from app.ml.gan_ae import GanAEDetector
from app.ml.isolation_forest import IsolationForestDetector
from app.ml.registry import (
    DetectorManager,
    DetectorRegistry,
    DetectorRegistryError,
)
from app.ml.stalwart import StalwartDetector
from app.ml.voting import VotingDetector

__all__ = [
    "BASELINE_READING_TARGET",
    "BaseDetector",
    "BaselineLearner",
    "BaselineStatus",
    "DetectionResult",
    "DetectorManager",
    "DetectorRegistry",
    "DetectorRegistryError",
    "GanAEDetector",
    "IsolationForestDetector",
    "StalwartDetector",
    "VotingDetector",
]
