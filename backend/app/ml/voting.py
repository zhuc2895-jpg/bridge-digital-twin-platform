"""Three-model majority voting orchestration behind one detector contract."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

from app.ml.contracts import (
    BaseDetector,
    BaselineStatus,
    DetectionResult,
    ReadingPredicate,
)
from app.ml.gan_ae import GanAEDetector
from app.ml.isolation_forest import IsolationForestDetector
from app.ml.stalwart import StalwartDetector
from app.ml.voting_policy import (
    CONFIDENCE_THRESHOLD,
    MIN_VOTES,
    MajorityVotePolicy,
)

logger = logging.getLogger(__name__)


class VotingDetector(BaseDetector):
    """Run three independent models and apply the fixed majority policy."""

    detector_id = "ensemble"
    display_name = "STALWART + GAN-AE + Isolation Forest"

    def __init__(
        self,
        detectors: Sequence[BaseDetector] | None = None,
        *,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        min_votes: int = MIN_VOTES,
    ) -> None:
        self.detectors = list(
            detectors
            if detectors is not None
            else [
                StalwartDetector(),
                GanAEDetector(),
                IsolationForestDetector(),
            ]
        )
        if len(self.detectors) < 2:
            raise ValueError("VotingDetector requires at least two model detectors")
        detector_ids = [detector.detector_id for detector in self.detectors]
        if len(set(detector_ids)) != len(detector_ids):
            raise ValueError("model detector ids must be unique")

        self.policy = MajorityVotePolicy(
            confidence_threshold=confidence_threshold,
            min_votes=min_votes,
        )
        self._normal_details = self.policy.known_normal(self.detectors).to_details(
            confidence_threshold=self.policy.confidence_threshold,
        )
        self._total_detections = 0
        self._alerts_triggered = 0
        self._model_failures: dict[str, str] = {}

    @property
    def parameters(self) -> dict[str, float | int | list[str]]:
        return {
            "confidence_threshold": self.policy.confidence_threshold,
            "min_votes": self.policy.min_votes,
            "models": [detector.detector_id for detector in self.detectors],
        }

    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        statuses = [
            detector.learn_baseline(reading, is_normal=is_normal)
            for detector in self.detectors
        ]
        return self._aggregate_status(str(reading["sensor_id"]), statuses)

    def get_baseline_status(
        self,
        sensor_id: str | None = None,
    ) -> BaselineStatus | dict[str, BaselineStatus]:
        if sensor_id is not None:
            return self._aggregate_status(
                sensor_id,
                [
                    self._single_status(detector, sensor_id)
                    for detector in self.detectors
                ],
            )

        all_statuses: dict[str, list[BaselineStatus]] = {}
        for detector in self.detectors:
            sensor_statuses = detector.get_baseline_status()
            if not isinstance(sensor_statuses, dict):
                raise TypeError("get_baseline_status(None) must return a mapping")
            for current_sensor_id, status in sensor_statuses.items():
                all_statuses.setdefault(current_sensor_id, []).append(status)
        return {
            current_sensor_id: self._aggregate_status(
                current_sensor_id,
                statuses,
            )
            for current_sensor_id, statuses in all_statuses.items()
        }

    def reset_baseline(self, sensor_id: str | None = None) -> None:
        errors: list[Exception] = []
        for detector in self.detectors:
            try:
                detector.reset_baseline(sensor_id)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise RuntimeError(
                f"failed to reset {len(errors)} voting model baselines"
            ) from errors[0]

    def detect_one(self, reading: Mapping[str, Any]) -> DetectionResult:
        started = time.perf_counter()
        results: list[DetectionResult | None] = []
        for detector in self.detectors:
            try:
                results.append(detector.detect_one(reading))
            except Exception as exc:
                self._record_failure(detector.detector_id, exc)
                results.append(None)
        elapsed_ms = (time.perf_counter() - started) * 1000
        sensor_id = str(reading["sensor_id"])
        readiness = {
            detector.detector_id: self._ready_or_record_failure(
                detector,
                sensor_id,
            )
            for detector in self.detectors
        }
        tally = self.policy.tally(self.detectors, results, readiness)
        result = self.policy.result(
            reading,
            tally,
            detector_id=self.detector_id,
            inference_elapsed_ms=elapsed_ms,
        )
        if result.anomalous:
            self._alerts_triggered += 1
        self._total_detections += 1
        return result

    def detect_batch(
        self,
        readings: Sequence[Mapping[str, Any]],
        *,
        normal_predicate: ReadingPredicate | None = None,
    ) -> list[DetectionResult]:
        batch = list(readings)
        steady_results = self._steady_results_if_safe(batch, normal_predicate)
        if steady_results is not None:
            return steady_results
        return self._run_model_batches(batch, normal_predicate)

    def _steady_results_if_safe(
        self,
        batch: list[Mapping[str, Any]],
        normal_predicate: ReadingPredicate | None,
    ) -> list[DetectionResult] | None:
        if len(batch) < 2:
            return None
        sensor_id = str(batch[0]["sensor_id"])
        value = float(batch[0]["value"])
        if any(
            str(reading["sensor_id"]) != sensor_id or float(reading["value"]) != value
            for reading in batch
        ):
            return None
        if normal_predicate is not None and any(
            not normal_predicate(reading) for reading in batch
        ):
            return None

        required = max(
            self._single_status(detector, sensor_id).required_readings
            for detector in self.detectors
        )
        if len(batch) < required:
            return None

        prefix = self._run_model_batches(batch[:required], normal_predicate)
        statuses = [
            self._single_status(detector, sensor_id) for detector in self.detectors
        ]
        known_steady_normal = all(
            status.ready
            and status.mean is not None
            and abs(float(status.std or 0.0)) <= 1e-12
            and abs(value - float(status.mean)) <= 1e-12
            for status in statuses
        )
        if not known_steady_normal:
            remainder = self._run_model_batches(batch[required:], normal_predicate)
            return [*prefix, *remainder]
        return [
            *prefix,
            *[self._normal_batch_result(reading) for reading in batch[required:]],
        ]

    def _run_model_batches(
        self,
        batch: list[Mapping[str, Any]],
        normal_predicate: ReadingPredicate | None,
    ) -> list[DetectionResult]:
        model_results: list[list[DetectionResult | None]] = []
        for detector in self.detectors:
            try:
                results = detector.detect_batch(
                    batch,
                    normal_predicate=normal_predicate,
                )
                if len(results) != len(batch):
                    raise ValueError(
                        f"{detector.detector_id} returned {len(results)} "
                        f"results for {len(batch)} readings"
                    )
                model_results.append(list(results))
            except Exception as exc:
                self._record_failure(detector.detector_id, exc)
                model_results.append([None] * len(batch))

        combined = []
        for index, current_reading in enumerate(batch):
            current_results = [results[index] for results in model_results]
            if not any(
                result is not None and result.anomalous for result in current_results
            ) and all(
                result is not None
                and not result.reason.startswith("baseline_")
                and result.details.get("model_ready") is not False
                for result in current_results
            ):
                combined.append(self._normal_batch_result(current_reading))
                continue

            sensor_id = str(current_reading["sensor_id"])
            readiness = {
                detector.detector_id: self._ready_or_record_failure(
                    detector,
                    sensor_id,
                )
                for detector in self.detectors
            }
            tally = self.policy.tally(
                self.detectors,
                current_results,
                readiness,
            )
            result = self.policy.result(
                current_reading,
                tally,
                detector_id=self.detector_id,
            )
            if result.anomalous:
                self._alerts_triggered += 1
            self._total_detections += 1
            combined.append(result)
        return combined

    def _normal_batch_result(
        self,
        reading: Mapping[str, Any],
    ) -> DetectionResult:
        self._total_detections += 1
        sensor_id = str(reading["sensor_id"])
        return DetectionResult(
            sensor_id=sensor_id,
            name=str(reading.get("name", sensor_id)),
            value=float(reading["value"]),
            timestamp=float(reading["timestamp"]),
            detector_id=self.detector_id,
            anomalous=False,
            score=0.0,
            confidence=0.0,
            reason="known normal batch",
            details=self._normal_details,
        )

    def get_stats(self) -> dict:
        models = []
        total_detections = 0
        for detector in self.detectors:
            try:
                stats = detector.get_stats()
                statuses = detector.get_baseline_status()
            except Exception as exc:
                self._record_failure(detector.detector_id, exc)
                stats = {}
                statuses = {}
            total_detections += int(stats.get("total_detections", 0))
            sensors = {}
            if isinstance(statuses, dict):
                for sensor_id, status in statuses.items():
                    sensors[sensor_id] = {
                        "ready": status.ready,
                        "readings": status.readings,
                    }
            models.append(
                {
                    "id": detector.detector_id,
                    "name": detector.display_name or detector.detector_id,
                    "source": detector.source,
                    "health": (
                        "degraded"
                        if detector.detector_id in self._model_failures
                        else "healthy"
                    ),
                    "last_error": self._model_failures.get(detector.detector_id),
                    "sensors": sensors,
                    "stats": stats,
                }
            )

        return {
            "health": "degraded" if self._model_failures else "healthy",
            "failure_count": len(self._model_failures),
            "total_detections": total_detections,
            "ml_alerts_triggered": self._alerts_triggered,
            "voting": self.parameters,
            "models": models,
        }

    @staticmethod
    def _single_status(
        detector: BaseDetector,
        sensor_id: str,
    ) -> BaselineStatus:
        status = detector.get_baseline_status(sensor_id)
        if not isinstance(status, BaselineStatus):
            raise TypeError("single-sensor baseline lookup must return BaselineStatus")
        return status

    def _ready_or_record_failure(
        self,
        detector: BaseDetector,
        sensor_id: str,
    ) -> bool:
        try:
            return self._single_status(detector, sensor_id).ready
        except Exception as exc:
            self._record_failure(detector.detector_id, exc)
            return False

    @staticmethod
    def _aggregate_status(
        sensor_id: str,
        statuses: Sequence[BaselineStatus],
    ) -> BaselineStatus:
        if not statuses:
            return BaselineStatus(
                sensor_id=sensor_id,
                readings=0,
                required_readings=100,
                state="learning",
            )
        states = {status.state for status in statuses}
        if "relearning" in states:
            state = "relearning"
        elif states == {"ready"}:
            state = "ready"
        else:
            state = "learning"
        primary = statuses[0]
        return BaselineStatus(
            sensor_id=sensor_id,
            readings=min(status.readings for status in statuses),
            required_readings=max(status.required_readings for status in statuses),
            state=state,
            mean=primary.mean,
            std=primary.std,
            ema_fast=primary.ema_fast,
            ema_slow=primary.ema_slow,
        )

    def _record_failure(self, detector_id: str, exc: Exception) -> None:
        self._model_failures[detector_id] = f"{type(exc).__name__}: {exc}"
        logger.exception("Voting model %s failed", detector_id)
