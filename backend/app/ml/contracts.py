"""Shared contracts for pluggable anomaly detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from app.alert_contracts import AI_ALERT_SOURCES

BASELINE_READING_TARGET = 100


ReadingPredicate = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class DetectionResult:
    """One detector's verdict for one sensor reading."""

    sensor_id: str
    name: str
    value: float
    timestamp: float
    detector_id: str
    anomalous: bool
    score: float = 0.0
    confidence: float = 0.0
    reason: str = ""
    level: str | None = None
    source: str | None = None
    message: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.anomalous and self.source not in AI_ALERT_SOURCES:
            raise ValueError(
                f"anomalous detector result requires a canonical AI source: {self.source}"
            )
        if self.source is not None and self.source not in AI_ALERT_SOURCES:
            raise ValueError(f"unknown AI alert source: {self.source}")


@dataclass(frozen=True)
class BaselineStatus:
    """Observable baseline-learning state for one detector and sensor."""

    sensor_id: str
    readings: int
    required_readings: int
    state: str
    mean: float | None = None
    std: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None

    @property
    def ready(self) -> bool:
        return self.state == "ready"

    def to_dict(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "readings": self.readings,
            "required_readings": self.required_readings,
            "state": self.state,
            "ready": self.ready,
            "mean": self.mean,
            "std": self.std,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
        }


class BaseDetector(ABC):
    """Extension seam for anomaly detector implementations."""

    detector_id = ""
    display_name = ""
    source: str | None = None

    @abstractmethod
    def detect_one(self, reading: Mapping[str, Any]) -> DetectionResult:
        """Evaluate one sensor reading."""

    @abstractmethod
    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        """Consume one candidate reading while a sensor baseline is learning."""

    @abstractmethod
    def get_baseline_status(
        self,
        sensor_id: str | None = None,
    ) -> BaselineStatus | dict[str, BaselineStatus]:
        """Return one sensor's baseline status, or every tracked sensor's status."""

    @abstractmethod
    def reset_baseline(self, sensor_id: str | None = None) -> None:
        """Start a fresh baseline for one sensor or every known sensor."""

    @abstractmethod
    def get_stats(self) -> dict:
        """Return detector-specific operational statistics."""

    def make_result(
        self,
        reading: Mapping[str, Any],
        *,
        anomalous: bool,
        score: float = 0.0,
        confidence: float = 0.0,
        reason: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> DetectionResult:
        """Build a detector result with this detector's identity and source."""
        sensor_id = str(reading["sensor_id"])
        name = str(reading.get("name", sensor_id))
        return DetectionResult(
            sensor_id=sensor_id,
            name=name,
            value=float(reading["value"]),
            timestamp=float(reading["timestamp"]),
            detector_id=self.detector_id,
            anomalous=anomalous,
            score=score,
            confidence=confidence,
            reason=reason,
            level=None,
            source=self.source,
            message=None,
            details=details or {},
        )

    def detect_batch(
        self,
        readings: Sequence[Mapping[str, Any]],
        *,
        normal_predicate: ReadingPredicate | None = None,
    ) -> list[DetectionResult]:
        """Evaluate a reading batch while honoring baseline warm-up."""
        results: list[DetectionResult] = []
        for reading in readings:
            sensor_id = str(reading["sensor_id"])
            status = self.get_baseline_status(sensor_id)
            if not isinstance(status, BaselineStatus):
                raise TypeError(
                    "single-sensor baseline lookup must return BaselineStatus"
                )

            if not status.ready:
                is_normal = (
                    normal_predicate(reading) if normal_predicate is not None else True
                )
                updated = self.learn_baseline(reading, is_normal=is_normal)
                results.append(
                    DetectionResult(
                        sensor_id=sensor_id,
                        name=str(reading.get("name", sensor_id)),
                        value=float(reading["value"]),
                        timestamp=float(reading["timestamp"]),
                        detector_id=self.detector_id,
                        anomalous=False,
                        reason=f"baseline_{updated.state}",
                        details={"baseline": updated.to_dict()},
                    )
                )
                continue

            results.append(self.detect_one(reading))
        return results
