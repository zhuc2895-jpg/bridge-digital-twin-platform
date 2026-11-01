"""Detector registration, replacement, and guarded execution."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.ml.contracts import BaseDetector, DetectionResult, ReadingPredicate

logger = logging.getLogger(__name__)


class DetectorRegistryError(ValueError):
    """Invalid or conflicting detector registration."""


class DetectorRelearnError(DetectorRegistryError):
    """A baseline relearn could not reset every registered detector."""

    def __init__(
        self,
        sensor_id: str | None,
        detector_ids: list[str],
    ) -> None:
        self.sensor_id = sensor_id
        self.detector_ids = detector_ids
        target = sensor_id if sensor_id is not None else "all sensors"
        super().__init__(
            f"baseline relearn failed for {target}: "
            f"{", ".join(detector_ids)}"
        )


@dataclass
class _DetectorFailure:
    count: int = 0
    last_error: str = ""
    last_failed_at: float | None = None


class DetectorRegistry:
    """Ordered registry used to assemble detector plugins at startup."""

    def __init__(self, detectors: Iterable[BaseDetector] = ()) -> None:
        self._detectors: dict[str, BaseDetector] = {}
        for detector in detectors:
            self.register(detector)

    def register(self, detector: BaseDetector, *, replace: bool = False) -> None:
        self._validate(detector)
        if detector.detector_id in self._detectors and not replace:
            raise DetectorRegistryError(
                f"detector '{detector.detector_id}' is already registered"
            )
        self._detectors[detector.detector_id] = detector

    def replace(self, detector: BaseDetector) -> None:
        self.register(detector, replace=True)

    def unregister(self, detector_id: str) -> None:
        try:
            del self._detectors[detector_id]
        except KeyError as exc:
            raise DetectorRegistryError(
                f"detector '{detector_id}' is not registered"
            ) from exc

    def get(self, detector_id: str) -> BaseDetector:
        try:
            return self._detectors[detector_id]
        except KeyError as exc:
            raise DetectorRegistryError(
                f"detector '{detector_id}' is not registered"
            ) from exc

    def items(self) -> list[tuple[str, BaseDetector]]:
        return list(self._detectors.items())

    def __len__(self) -> int:
        return len(self._detectors)

    @staticmethod
    def _validate(detector: BaseDetector) -> None:
        if not isinstance(detector, BaseDetector):
            raise DetectorRegistryError("detector must implement BaseDetector")
        detector_id = detector.detector_id
        if not isinstance(detector_id, str) or not detector_id.strip():
            raise DetectorRegistryError("detector_id must be a non-empty string")


class DetectorManager:
    """Run registered detectors without allowing one failure to stop ingestion."""

    def __init__(self, registry: DetectorRegistry | None = None) -> None:
        self.registry = registry or DetectorRegistry()
        self._failures: dict[str, _DetectorFailure] = {}
        self._relearn_failures: dict[str, set[str]] = {}
        self._pending_detector_replacements: dict[str, set[str]] = {}

    def register_detector(
        self,
        detector: BaseDetector,
        *,
        replace: bool = False,
    ) -> None:
        self.registry.register(detector, replace=replace)
        self._failures[detector.detector_id] = _DetectorFailure()
        self._replace_relearn_failure(detector.detector_id)

    def replace_detector(self, detector: BaseDetector) -> None:
        self.register_detector(detector, replace=True)

    def detect(
        self,
        readings: Iterable[Mapping[str, Any]],
        *,
        normal_predicate: ReadingPredicate | None = None,
    ) -> list[DetectionResult]:
        batch = list(readings)
        detections: list[DetectionResult] = []
        for detector_id, detector in self.registry.items():
            try:
                results = detector.detect_batch(
                    batch,
                    normal_predicate=normal_predicate,
                )
                for result in results:
                    if not isinstance(result, DetectionResult):
                        raise TypeError("detect_batch must return DetectionResult values")
                    if result.anomalous and not self._ai_is_suppressed(
                        result.sensor_id
                    ):
                        detections.append(result)
            except Exception as exc:  # detector plugins are untrusted boundaries
                self._record_failure(detector_id, exc)
        return detections

    def relearn(self, sensor_id: str | None = None) -> dict:
        reset_ids: list[str] = []
        failed_ids: list[str] = []
        for detector_id, detector in self.registry.items():
            try:
                detector.reset_baseline(sensor_id)
                reset_ids.append(detector_id)
            except Exception as exc:
                failed_ids.append(detector_id)
                self._record_failure(detector_id, exc)

        if failed_ids:
            targets = (
                self._known_sensor_ids() if sensor_id is None else {sensor_id}
            )
            for target_sensor_id in targets:
                self._relearn_failures[target_sensor_id] = set(failed_ids)
            raise DetectorRelearnError(sensor_id, failed_ids)

        if sensor_id is None:
            self._relearn_failures.clear()
            self._pending_detector_replacements.clear()
        else:
            self._relearn_failures.pop(sensor_id, None)
            self._pending_detector_replacements.pop(sensor_id, None)

        if not reset_ids:
            raise DetectorRegistryError("no detector baseline could be reset")
        return {
            "status": "relearning",
            "sensor_id": sensor_id,
            "detectors": reset_ids,
        }

    def _replace_relearn_failure(self, detector_id: str) -> None:
        for sensor_id, failed_ids in list(self._relearn_failures.items()):
            if detector_id not in failed_ids:
                continue
            failed_ids.discard(detector_id)
            self._pending_detector_replacements.setdefault(sensor_id, set()).add(
                detector_id
            )
            if not failed_ids:
                del self._relearn_failures[sensor_id]

    def _ai_is_suppressed(self, sensor_id: str) -> bool:
        self._release_completed_replacements(sensor_id)
        return bool(
            self._relearn_failures.get(sensor_id)
            or self._pending_detector_replacements.get(sensor_id)
        )

    def _release_completed_replacements(self, sensor_id: str) -> None:
        if not self._pending_detector_replacements.get(sensor_id):
            return
        for detector_id, detector in self.registry.items():
            try:
                status = detector.get_baseline_status(sensor_id)
            except Exception as exc:
                self._record_failure(detector_id, exc)
                return
            if not getattr(status, "ready", False):
                return
        self._pending_detector_replacements.pop(sensor_id, None)

    def _known_sensor_ids(self) -> set[str]:
        sensor_ids: set[str] = set()
        for _, detector in self.registry.items():
            try:
                statuses = detector.get_baseline_status()
            except Exception as exc:
                self._record_failure(detector.detector_id, exc)
                continue
            if isinstance(statuses, dict):
                sensor_ids.update(statuses)
        return sensor_ids

    def get_stats(self) -> dict:
        detector_stats: list[dict] = []
        total_detections = 0
        ml_alerts_triggered = 0
        baseline_readings = 0

        for detector_id, detector in self.registry.items():
            try:
                stats = detector.get_stats()
                statuses = detector.get_baseline_status()
                if not isinstance(statuses, dict):
                    raise TypeError(
                        "get_baseline_status(None) must return a mapping"
                    )
                sensors = {
                    sensor_id: status.to_dict()
                    for sensor_id, status in statuses.items()
                }
            except Exception as exc:
                self._record_failure(detector_id, exc)
                stats = {}
                sensors = {}

            detector_detections = int(stats.get("total_detections", 0))
            detector_alerts = int(stats.get("ml_alerts_triggered", 0))
            total_detections += detector_detections
            ml_alerts_triggered += detector_alerts
            baseline_readings += sum(
                item["readings"] for item in sensors.values()
            )
            failure = self._failures.get(detector_id, _DetectorFailure())

            detector_stats.append(
                {
                    "id": detector_id,
                    "name": detector.display_name or detector_id,
                    "health": "degraded" if failure.count else "healthy",
                    "failure_count": failure.count,
                    "last_error": failure.last_error or None,
                    "last_failed_at": failure.last_failed_at,
                    "baseline": {
                        "required_readings": (
                            next(iter(sensors.values()))["required_readings"]
                            if sensors
                            else 100
                        ),
                        "sensors": sensors,
                    },
                    "stats": stats,
                }
            )

        return {
            "detector_count": len(self.registry),
            "total_detections": total_detections,
            "ml_alerts_triggered": ml_alerts_triggered,
            "baseline_readings": baseline_readings,
            "detectors": detector_stats,
        }

    def _record_failure(self, detector_id: str, exc: Exception) -> None:
        failure = self._failures.setdefault(detector_id, _DetectorFailure())
        failure.count += 1
        failure.last_error = f"{type(exc).__name__}: {exc}"
        failure.last_failed_at = time.time()
        logger.exception("Detector %s failed", detector_id)
