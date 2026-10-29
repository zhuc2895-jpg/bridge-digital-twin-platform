"""Three-model majority voting behind one detector contract."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

from app.ml.contracts import (
    BaselineStatus,
    BaseDetector,
    DetectionResult,
    ReadingPredicate,
)
from app.ml.gan_ae import GanAEDetector
from app.ml.isolation_forest import IsolationForestDetector
from app.ml.stalwart import StalwartDetector

logger = logging.getLogger(__name__)


class VotingDetector(BaseDetector):
    """Require at least two confident model votes before emitting an alert."""

    detector_id = "ensemble"
    display_name = "STALWART + GAN-AE + Isolation Forest"

    def __init__(
        self,
        detectors: Sequence[BaseDetector] | None = None,
        *,
        confidence_threshold: float = 0.7,
        min_votes: int = 2,
    ) -> None:
        if confidence_threshold != 0.7:
            raise ValueError("confidence_threshold must be exactly 0.7")
        if min_votes != 2:
            raise ValueError("min_votes must be exactly two")

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

        self.confidence_threshold = float(confidence_threshold)
        self.min_votes = min_votes
        self._total_detections = 0
        self._alerts_triggered = 0
        self._model_failures: dict[str, str] = {}

    @property
    def parameters(self) -> dict[str, float | int | list[str]]:
        return {
            "confidence_threshold": self.confidence_threshold,
            "min_votes": self.min_votes,
            "models": [detector.detector_id for detector in self.detectors],
        }

    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        statuses = []
        for detector in self.detectors:
            statuses.append(detector.learn_baseline(reading, is_normal=is_normal))
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
        return self._combine(
            reading,
            results,
            inference_elapsed_ms=elapsed_ms,
        )

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
            combined.append(
                self._combine(
                    current_reading,
                    current_results,
                    inference_elapsed_ms=None,
                )
            )
        return combined

    def _normal_batch_result(
        self,
        reading: Mapping[str, Any],
    ) -> DetectionResult:
        sensor_id = str(reading["sensor_id"])
        self._total_detections += 1
        return DetectionResult(
            sensor_id=sensor_id,
            name=str(reading.get("name", sensor_id)),
            value=float(reading["value"]),
            timestamp=float(reading["timestamp"]),
            detector_id=self.detector_id,
            anomalous=False,
            reason="no model voted anomaly",
            details={"vote_count": 0, "participating_models": []},
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

    def _combine(
        self,
        reading: Mapping[str, Any],
        results: Sequence[DetectionResult | None],
        *,
        inference_elapsed_ms: float | None,
    ) -> DetectionResult:
        model_results: dict[str, dict[str, Any]] = {}
        votes: dict[str, bool] = {}
        scores: dict[str, float] = {}
        confidences: dict[str, float] = {}
        participating: list[str] = []
        ready_models: list[str] = []
        sensor_id = str(reading["sensor_id"])

        for detector, result in zip(self.detectors, results, strict=True):
            model_id = detector.detector_id
            ready = self._model_is_ready(detector, sensor_id)
            if ready:
                ready_models.append(model_id)
            confidence = float(result.confidence) if result is not None else 0.0
            score = float(result.score) if result is not None else 0.0
            vote = bool(
                ready
                and result is not None
                and result.anomalous
                and confidence >= self.confidence_threshold
            )
            votes[model_id] = vote
            scores[model_id] = score
            confidences[model_id] = confidence
            if vote:
                participating.append(model_id)
            model_results[model_id] = {
                "source": (result.source if result is not None else detector.source),
                "ready": ready,
                "vote": vote,
                "raw_anomalous": (result.anomalous if result is not None else False),
                "confidence": confidence,
                "score": score,
                "reason": result.reason if result is not None else "model_failed",
            }

        vote_count = len(participating)
        details = {
            "votes": votes,
            "scores": scores,
            "confidences": confidences,
            "vote_count": vote_count,
            "participating_models": participating,
            "triggered_models": list(participating),
            "ready_models": ready_models,
            "model_ready": bool(ready_models),
            "model_results": model_results,
            "confidence_threshold": self.confidence_threshold,
            "min_votes": self.min_votes,
            "voting_parameters": self.parameters,
        }
        if inference_elapsed_ms is not None:
            details["inference_elapsed_ms"] = round(inference_elapsed_ms, 3)

        if vote_count >= self.min_votes:
            self._alerts_triggered += 1
            self._total_detections += 1
            level = "red" if vote_count >= 3 else "orange"
            confidence = max(confidences[model_id] for model_id in participating)
            score = max(scores[model_id] for model_id in participating)
            details["level_reason"] = (
                "all three models confirmed"
                if vote_count >= 3
                else "two independent models confirmed"
            )
            return DetectionResult(
                sensor_id=sensor_id,
                name=str(reading.get("name", sensor_id)),
                value=float(reading["value"]),
                timestamp=float(reading["timestamp"]),
                detector_id=self.detector_id,
                anomalous=True,
                score=score,
                confidence=confidence,
                reason="at least two confident detectors voted anomaly",
                level=level,
                source="ai_dual_confirm",
                message=(
                    f"[AI多模型确认] {reading.get('name', sensor_id)} 异常 "
                    f"(投票:{'+'.join(participating)}, 置信度:{confidence:.0%})"
                ),
                details=details,
            )

        self._total_detections += 1
        return DetectionResult(
            sensor_id=sensor_id,
            name=str(reading.get("name", sensor_id)),
            value=float(reading["value"]),
            timestamp=float(reading["timestamp"]),
            detector_id=self.detector_id,
            anomalous=False,
            score=max(scores.values(), default=0.0),
            confidence=max(confidences.values(), default=0.0),
            reason=(
                "insufficient confident model votes"
                if ready_models
                else "models_not_ready"
            ),
            details=details,
        )

    @staticmethod
    def _single_status(
        detector: BaseDetector,
        sensor_id: str,
    ) -> BaselineStatus:
        status = detector.get_baseline_status(sensor_id)
        if not isinstance(status, BaselineStatus):
            raise TypeError("single-sensor baseline lookup must return BaselineStatus")
        return status

    def _model_is_ready(self, detector: BaseDetector, sensor_id: str) -> bool:
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
