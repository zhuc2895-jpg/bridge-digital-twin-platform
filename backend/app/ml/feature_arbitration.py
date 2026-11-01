"""Third-layer multi-window feature arbitration for AI anomaly candidates."""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from app.ml.contracts import (
    BaseDetector,
    BaselineStatus,
    DetectionResult,
    ReadingPredicate,
)
from app.ml.spatial_residual import SpatialEvidence, SpatialResidualModel

MEAN_SHIFT_THRESHOLD = 2.0
VARIANCE_CHANGE_THRESHOLD = 2.0
TREND_SLOPE_THRESHOLD = 2.0
REQUIRED_EXCEEDED_FEATURES = 2
RECENT_WINDOW_SIZE = 20
HISTORICAL_WINDOW_SIZE = 60
MAX_RETAINED_READINGS = 1_000


@dataclass(frozen=True)
class ArbitrationDecision:
    """Explainable output from one multi-window feature comparison."""

    available: bool
    window_available: int
    window_required: int
    recent_window_size: int
    historical_window_size: int
    features: dict[str, float]
    feature_evidence: dict[str, dict[str, Any]]
    exceeded_features: list[str]
    thresholds: dict[str, float]
    required_features: int
    conclusion: str
    level: str | None
    recent_mean: float | None = None
    historical_mean: float | None = None
    recent_standard_deviation: float | None = None
    historical_standard_deviation: float | None = None
    raw_trend_slope: float | None = None
    spatial: dict[str, Any] = field(default_factory=dict)
    spatial_action: str = "not_applicable"

    def to_details(self) -> dict[str, Any]:
        details: dict[str, Any] = {
            "window": {
                "available": self.available,
                "observed": self.window_available,
                "required": self.window_required,
                "recent_size": self.recent_window_size,
                "historical_size": self.historical_window_size,
            },
            "features": dict(self.features),
            "feature_evidence": {
                name: dict(evidence)
                for name, evidence in self.feature_evidence.items()
            },
            "thresholds": dict(self.thresholds),
            "required_features": self.required_features,
            "exceeded_features": list(self.exceeded_features),
            "exceeded_count": len(self.exceeded_features),
            "final_conclusion": self.conclusion,
            "spatial": dict(self.spatial),
            "spatial_action": self.spatial_action,
        }
        if self.available:
            details.update(
                {
                    "recent_mean": self.recent_mean,
                    "historical_mean": self.historical_mean,
                    "recent_standard_deviation": (
                        self.recent_standard_deviation
                    ),
                    "historical_standard_deviation": (
                        self.historical_standard_deviation
                    ),
                    "raw_trend_slope": self.raw_trend_slope,
                }
            )
        return details


@dataclass(frozen=True)
class _HistoryReading:
    sensor_id: str
    timestamp: float
    sequence: int
    reading: dict[str, Any]


@dataclass
class _SensorHistoryState:
    entries: list[_HistoryReading] = field(default_factory=list)
    latest_timestamp: float | None = None


class FeatureArbitrator:
    """Maintain per-sensor windows and classify model candidates."""

    def __init__(
        self,
        *,
        mean_shift_threshold: float = MEAN_SHIFT_THRESHOLD,
        variance_change_threshold: float = VARIANCE_CHANGE_THRESHOLD,
        trend_slope_threshold: float = TREND_SLOPE_THRESHOLD,
        required_features: int = REQUIRED_EXCEEDED_FEATURES,
        spatial_model: SpatialResidualModel | None = None,
    ) -> None:
        if min(
            mean_shift_threshold,
            variance_change_threshold,
            trend_slope_threshold,
        ) <= 0:
            raise ValueError("feature thresholds must be positive")
        if required_features != REQUIRED_EXCEEDED_FEATURES:
            raise ValueError("required_features must be exactly two")

        self.recent_window_size = RECENT_WINDOW_SIZE
        self.historical_window_size = HISTORICAL_WINDOW_SIZE
        self.mean_shift_threshold = float(mean_shift_threshold)
        self.variance_change_threshold = float(variance_change_threshold)
        self.trend_slope_threshold = float(trend_slope_threshold)
        self.required_features = required_features
        self.spatial_model = spatial_model or SpatialResidualModel()
        self.window_required = self.recent_window_size + self.historical_window_size

        self._windows: dict[str, list[tuple[float, int, float]]] = {}
        self._observations: dict[str, int] = {}
        self._latest_decisions: dict[str, ArbitrationDecision] = {}
        self._latest_entries: dict[str, tuple[float, int]] = {}
        self._sequence = 0
        self._total_observed = 0
        self._confirmed = 0
        self._suspected = 0

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "recent_window_size": self.recent_window_size,
            "historical_window_size": self.historical_window_size,
            "window_required": self.window_required,
            "mean_shift_threshold": self.mean_shift_threshold,
            "variance_change_threshold": self.variance_change_threshold,
            "trend_slope_threshold": self.trend_slope_threshold,
            "required_features": self.required_features,
            "spatial_residual": self.spatial_model.parameters,
        }

    def observe_spatial_reading(self, reading: Mapping[str, Any]) -> None:
        self.spatial_model.observe_reading(reading)

    def observe(self, reading: Mapping[str, Any]) -> ArbitrationDecision:
        """Append one reading and return the current window decision."""
        return self.observe_many([reading])[0]

    def observe_many(
        self,
        readings: Sequence[Mapping[str, Any]],
    ) -> list[ArbitrationDecision]:
        """Append a batch and return one decision per reading."""
        decisions = self._observe_batch(
            readings,
            evaluation_indices=set(range(len(readings))),
        )
        return [decisions[index] for index in range(len(readings))]

    def observe_selected(
        self,
        readings: Sequence[Mapping[str, Any]],
        evaluation_indices: Sequence[int],
    ) -> dict[int, ArbitrationDecision]:
        """Insert every reading but evaluate only selected batch positions."""
        return self._observe_batch(
            readings,
            evaluation_indices=set(evaluation_indices),
        )

    def _observe_batch(
        self,
        readings: Sequence[Mapping[str, Any]],
        *,
        evaluation_indices: set[int],
    ) -> dict[int, ArbitrationDecision]:
        batch = list(readings)
        if not batch:
            return {}

        self.spatial_model.observe_batch(batch)
        spatial_evidence = self._spatial_evidence_for_batch(batch)
        prepared: list[tuple[int, str, tuple[float, int, float]]] = []
        touched_sensors: set[str] = set()
        for reading in batch:
            sensor_id = str(reading["sensor_id"])
            value = float(reading["value"])
            timestamp = float(reading["timestamp"])
            self._sequence += 1
            entry = (timestamp, self._sequence, value)
            window = self._windows.setdefault(sensor_id, [])
            insertion_index = bisect_right(
                window,
                (timestamp, self._sequence, math.inf),
            )
            window.insert(insertion_index, entry)
            prepared.append((len(prepared), sensor_id, entry))
            touched_sensors.add(sensor_id)
            self._observations[sensor_id] = (
                self._observations.get(sensor_id, 0) + 1
            )
            self._total_observed += 1

        decisions: dict[int, ArbitrationDecision] = {}
        for index, sensor_id, entry in prepared:
            latest_entry = self._latest_entries.get(sensor_id)
            if latest_entry is None or entry[:2] > latest_entry:
                self._latest_entries[sensor_id] = entry[:2]
            if index not in evaluation_indices:
                continue

            window = self._windows[sensor_id]
            timestamp, sequence, _ = entry
            insertion_index = bisect_right(
                window,
                (timestamp, sequence, math.inf),
            )
            window_start = max(0, insertion_index - self.window_required)
            event_window = [
                current_value
                for _, _, current_value in window[
                    window_start:insertion_index
                ]
            ]
            decision = self._decide(
                event_window,
                window_available=len(event_window),
                spatial_evidence=spatial_evidence.get(index),
            )
            decisions[index] = decision
            if decision.conclusion == "confirmed":
                self._confirmed += 1
            elif decision.conclusion == "suspected":
                self._suspected += 1

            if entry[:2] == self._latest_entries[sensor_id]:
                self._latest_decisions[sensor_id] = decision

        for sensor_id in touched_sensors:
            window = self._windows[sensor_id]
            if len(window) > MAX_RETAINED_READINGS:
                del window[: len(window) - MAX_RETAINED_READINGS]
        return decisions

    def _spatial_evidence_for_batch(
        self,
        readings: Sequence[Mapping[str, Any]],
    ) -> dict[int, SpatialEvidence]:
        snapshots: dict[float, dict[str, float]] = {}
        for reading in readings:
            try:
                timestamp = float(reading["timestamp"])
                value = float(reading["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(timestamp) or not math.isfinite(value):
                continue
            snapshots.setdefault(timestamp, {})[str(reading["sensor_id"])] = value

        cache: dict[float, dict[str, SpatialEvidence]] = {}
        evidence_by_index: dict[int, SpatialEvidence] = {}
        for index, reading in enumerate(readings):
            try:
                timestamp = float(reading["timestamp"])
            except (KeyError, TypeError, ValueError):
                continue
            sensor_id = str(reading["sensor_id"])
            if timestamp not in cache:
                cache[timestamp] = self.spatial_model.evaluate_snapshot(
                    snapshots.get(timestamp, {})
                )
            evidence = cache[timestamp].get(sensor_id)
            if evidence is None:
                reason = (
                    "model_not_ready"
                    if not self.spatial_model.ready
                    else "sensor_unavailable"
                )
                evidence = self.spatial_model.unavailable(sensor_id, reason)
            evidence_by_index[index] = evidence
        return evidence_by_index

    def reset(self, sensor_id: str | None = None) -> None:
        if sensor_id is None:
            self.reset_windows()
            self._total_observed = 0
            self._confirmed = 0
            self._suspected = 0
            self.spatial_model.reset()
            return

        current_sensor_id = str(sensor_id)
        self._windows.pop(current_sensor_id, None)
        self._observations.pop(current_sensor_id, None)
        self._latest_decisions.pop(current_sensor_id, None)
        self._latest_entries.pop(current_sensor_id, None)

    def reset_windows(self) -> None:
        """Clear per-sensor event windows while keeping learned spatial state."""
        self._windows.clear()
        self._observations.clear()
        self._latest_decisions.clear()
        self._latest_entries.clear()
        self._sequence = 0

    def get_stats(self) -> dict[str, Any]:
        sensors = {}
        for sensor_id, count in self._observations.items():
            latest = self._latest_decisions.get(sensor_id)
            sensors[sensor_id] = {
                "readings": count,
                "window_available": bool(
                    latest.available
                    if latest is not None
                    else count >= self.window_required
                ),
                "latest_conclusion": latest.conclusion if latest else None,
                "latest_exceeded_features": (
                    list(latest.exceeded_features) if latest else []
                ),
            }
        return {
            "parameters": self.parameters,
            "total_observed": self._total_observed,
            "confirmed_decisions": self._confirmed,
            "suspected_decisions": self._suspected,
            "spatial_residual": self.spatial_model.get_stats(),
            "sensors": sensors,
        }

    def evaluate_values(
        self,
        historical_values: Sequence[float],
        recent_values: Sequence[float],
    ) -> ArbitrationDecision:
        """Evaluate explicit windows with this arbitrator's configuration."""
        values = [*historical_values, *recent_values]
        return self._decide(values, window_available=len(values))

    @staticmethod
    def decide_from_values(
        historical_values: Sequence[float],
        recent_values: Sequence[float],
    ) -> ArbitrationDecision:  # type: ignore[override]
        """Evaluate explicit windows with the default thresholds."""
        return FeatureArbitrator()._decide(
            [*historical_values, *recent_values],
            window_available=len(historical_values) + len(recent_values),
        )

    def _decide(
        self,
        values: Sequence[float],
        *,
        window_available: int,
        spatial_evidence: SpatialEvidence | None = None,
    ) -> ArbitrationDecision:
        spatial_details = (
            spatial_evidence.to_details() if spatial_evidence is not None else {}
        )
        if len(values) < self.window_required:
            return ArbitrationDecision(
                available=False,
                window_available=window_available,
                window_required=self.window_required,
                recent_window_size=self.recent_window_size,
                historical_window_size=self.historical_window_size,
                features={},
                feature_evidence={},
                exceeded_features=[],
                thresholds=self._thresholds,
                required_features=self.required_features,
                conclusion="insufficient_window",
                level=None,
                spatial=spatial_details,
                spatial_action="not_applied",
            )

        historical = [
            float(value)
            for value in values[
                -self.window_required : -self.recent_window_size
            ]
        ]
        recent = [float(value) for value in values[-self.recent_window_size :]]
        historical_mean = _mean(historical)
        recent_mean = _mean(recent)
        historical_std = _population_standard_deviation(
            historical,
            historical_mean,
        )
        recent_std = _population_standard_deviation(recent, recent_mean)
        scale_floor = max(
            max(abs(historical_mean), abs(recent_mean), 1.0) * 1e-6,
            1e-9,
        )
        historical_scale = max(historical_std, scale_floor)

        mean_shift = _bounded(recent_mean - historical_mean, historical_scale)
        variance_change = _variance_change(recent_std, historical_std, scale_floor)
        raw_trend_slope = _linear_slope(recent)
        normalized_trend_slope = _bounded(
            raw_trend_slope * (self.recent_window_size - 1),
            historical_scale,
        )
        raw_trend_threshold = (
            self.trend_slope_threshold
            * historical_scale
            / (self.recent_window_size - 1)
        )
        thresholds = {
            "mean_shift": self.mean_shift_threshold,
            "variance_change": self.variance_change_threshold,
            "trend_slope": raw_trend_threshold,
        }

        feature_evidence = {
            "mean_shift": _feature_evidence(
                value=mean_shift,
                threshold=self.mean_shift_threshold,
                exceeded=abs(mean_shift) > self.mean_shift_threshold,
                direction=_direction(mean_shift),
            ),
            "variance_change": _feature_evidence(
                value=variance_change,
                threshold=self.variance_change_threshold,
                exceeded=variance_change > self.variance_change_threshold,
                direction=(
                    "increase"
                    if variance_change > 1.0
                    else "decrease" if variance_change < 1.0 else "stable"
                ),
            ),
            "trend_slope": _feature_evidence(
                value=raw_trend_slope,
                threshold=raw_trend_threshold,
                exceeded=abs(raw_trend_slope) > raw_trend_threshold,
                direction=_direction(raw_trend_slope),
                raw_value=raw_trend_slope,
                normalized_value=normalized_trend_slope,
            ),
        }
        features = {
            name: float(evidence["value"])
            for name, evidence in feature_evidence.items()
        }
        exceeded_features = [
            name for name, evidence in feature_evidence.items() if evidence["exceeded"]
        ]
        if len(exceeded_features) >= self.required_features:
            conclusion = "confirmed"
            level = "red" if len(exceeded_features) >= 3 else "orange"
        elif exceeded_features:
            conclusion = "suspected"
            level = "yellow"
        else:
            conclusion = "normal"
            level = None

        spatial_action = "not_applied"
        if spatial_evidence is not None:
            if (
                spatial_evidence.status == "isolated_outlier"
                and conclusion == "confirmed"
            ):
                conclusion = "suspected"
                level = "yellow"
                spatial_action = "capped_isolated_outlier"
            elif spatial_evidence.status == "coherent" and conclusion in {
                "confirmed",
                "suspected",
            }:
                spatial_action = "coherent_support"
            elif spatial_evidence.status == "consistent":
                spatial_action = "consistent"
            elif not spatial_evidence.available:
                spatial_action = "unavailable"

        return ArbitrationDecision(
            available=True,
            window_available=window_available,
            window_required=self.window_required,
            recent_window_size=self.recent_window_size,
            historical_window_size=self.historical_window_size,
            features=features,
            feature_evidence=feature_evidence,
            exceeded_features=exceeded_features,
            thresholds=thresholds,
            required_features=self.required_features,
            conclusion=conclusion,
            level=level,
            recent_mean=_rounded(recent_mean),
            historical_mean=_rounded(historical_mean),
            recent_standard_deviation=_rounded(recent_std),
            historical_standard_deviation=_rounded(historical_std),
            raw_trend_slope=_rounded(raw_trend_slope),
            spatial=spatial_details,
            spatial_action=spatial_action,
        )

    @property
    def _thresholds(self) -> dict[str, float]:
        return {
            "mean_shift": self.mean_shift_threshold,
            "variance_change": self.variance_change_threshold,
            "trend_slope": self.trend_slope_threshold,
        }


class FeatureArbitrationDetector(BaseDetector):
    """Apply feature arbitration only when layer-two models disagree."""

    detector_id = "ensemble"
    display_name = "Three-layer anomaly detector"

    def __init__(
        self,
        detector: BaseDetector,
        *,
        arbitrator: FeatureArbitrator | None = None,
        normal_predicate: ReadingPredicate | None = None,
    ) -> None:
        self.detector = detector
        self.arbitrator = arbitrator or FeatureArbitrator()
        self.normal_predicate = normal_predicate
        self._history: dict[str, _SensorHistoryState] = {}
        self._history_sequence = 0
        self._total_detections = 0
        self._alerts_triggered = 0

    @property
    def parameters(self) -> dict[str, Any]:
        inner_parameters = getattr(self.detector, "parameters", {})
        if not isinstance(inner_parameters, Mapping):
            inner_parameters = {}
        return {
            **dict(inner_parameters),
            "feature_arbitration": self.arbitrator.parameters,
        }

    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        status = self.detector.learn_baseline(reading, is_normal=is_normal)
        if is_normal:
            self.arbitrator.observe(reading)
            self.arbitrator.observe_spatial_reading(reading)
        entry = self._history_entry(reading)
        state = self._sensor_history(entry.sensor_id)
        state.entries.append(entry)
        self._update_latest_timestamp(state, entry.timestamp)
        self._trim_history(state)
        return status

    def get_baseline_status(
        self,
        sensor_id: str | None = None,
    ) -> BaselineStatus | dict[str, BaselineStatus]:
        return self.detector.get_baseline_status(sensor_id)

    def reset_baseline(self, sensor_id: str | None = None) -> None:
        self.detector.reset_baseline(sensor_id)
        self.arbitrator.reset(sensor_id)
        if sensor_id is None:
            self._history.clear()
            self._history_sequence = 0
            return
        current_sensor_id = str(sensor_id)
        self._history.pop(current_sensor_id, None)

    def flush(self) -> None:
        flush = getattr(self.detector, "flush", None)
        if callable(flush):
            flush()

    def reset_arbitration_history(self) -> None:
        """Start a new recording with fresh causal windows but trained models."""
        self.arbitrator.reset_windows()
        self._history.clear()
        self._history_sequence = 0

    def detect_one(self, reading: Mapping[str, Any]) -> DetectionResult:
        return self.detect_batch([reading])[0]

    def detect_batch(
        self,
        readings: Sequence[Mapping[str, Any]],
        *,
        normal_predicate: ReadingPredicate | None = None,
    ) -> list[DetectionResult]:
        batch = list(readings)
        if not batch:
            return []
        effective_normal_predicate = normal_predicate or self.normal_predicate
        batch_entries = [
            self._history_entry(reading)
            for reading in batch
        ]
        has_backfill = any(self._is_backfill(entry) for entry in batch_entries)

        if has_backfill:
            for entry in batch_entries:
                self._sensor_history(entry.sensor_id).entries.append(entry)
            self.detector.reset_baseline(None)
            current_by_sequence = {
                entry.sequence: index
                for index, entry in enumerate(batch_entries)
            }
            _, results_by_index = self._run_ordered_entries(
                self._all_history(),
                current_by_sequence,
                effective_normal_predicate,
            )
        else:
            current_by_sequence = {
                entry.sequence: index
                for index, entry in enumerate(batch_entries)
            }
            ordered_entries, results_by_index = self._run_ordered_entries(
                batch_entries,
                current_by_sequence,
                effective_normal_predicate,
            )
            for entry in ordered_entries:
                self._sensor_history(entry.sensor_id).entries.append(entry)

        for entry in batch_entries:
            state = self._sensor_history(entry.sensor_id)
            self._update_latest_timestamp(state, entry.timestamp)

        for state in self._history.values():
            self._trim_history(state)

        results = [results_by_index[index] for index in range(len(batch))]
        candidate_positions = [
            index
            for index, result in enumerate(results)
            if not result.anomalous
            and bool(self._triggered_models(result))
        ]
        decisions_by_index = self.arbitrator.observe_selected(
            batch,
            candidate_positions,
        )
        combined_results = [
            self._apply_arbitration(result, decisions_by_index.get(index))
            for index, result in enumerate(results)
        ]
        self._total_detections += len(combined_results)
        self._alerts_triggered += sum(
            result.anomalous for result in combined_results
        )
        return combined_results

    def _history_entry(
        self,
        reading: Mapping[str, Any],
    ) -> _HistoryReading:
        self._history_sequence += 1
        return _HistoryReading(
            sensor_id=str(reading["sensor_id"]),
            timestamp=float(reading["timestamp"]),
            sequence=self._history_sequence,
            reading=dict(reading),
        )

    def _all_history(self) -> list[_HistoryReading]:
        return [entry for state in self._history.values() for entry in state.entries]

    def _sensor_history(self, sensor_id: str) -> _SensorHistoryState:
        return self._history.setdefault(sensor_id, _SensorHistoryState())

    def _is_backfill(self, entry: _HistoryReading) -> bool:
        state = self._history.get(entry.sensor_id)
        return (
            state is not None
            and state.latest_timestamp is not None
            and entry.timestamp < state.latest_timestamp
        )

    @staticmethod
    def _update_latest_timestamp(
        state: _SensorHistoryState,
        timestamp: float,
    ) -> None:
        if state.latest_timestamp is None or timestamp > state.latest_timestamp:
            state.latest_timestamp = timestamp

    @staticmethod
    def _trim_history(state: _SensorHistoryState) -> None:
        state.entries.sort(key=lambda entry: (entry.timestamp, entry.sequence))
        if len(state.entries) > MAX_RETAINED_READINGS:
            del state.entries[: len(state.entries) - MAX_RETAINED_READINGS]

    def _run_ordered_entries(
        self,
        entries: Sequence[_HistoryReading],
        current_by_sequence: Mapping[int, int],
        normal_predicate: ReadingPredicate | None,
    ) -> tuple[list[_HistoryReading], dict[int, DetectionResult]]:
        ordered_entries = sorted(
            entries,
            key=lambda entry: (
                entry.sensor_id,
                entry.timestamp,
                entry.sequence,
            ),
        )
        ordered_results = self.detector.detect_batch(
            [entry.reading for entry in ordered_entries],
            normal_predicate=normal_predicate,
        )
        if len(ordered_results) != len(ordered_entries):
            raise ValueError(
                f"inner detector returned {len(ordered_results)} results "
                f"for {len(ordered_entries)} readings"
            )
        results_by_index: dict[int, DetectionResult] = {}
        for entry, result in zip(ordered_entries, ordered_results, strict=True):
            original_index = current_by_sequence.get(entry.sequence)
            if original_index is not None:
                results_by_index[original_index] = result
        return ordered_entries, results_by_index

    def get_stats(self) -> dict[str, Any]:
        stats = dict(self.detector.get_stats())
        stats["inner_reported_total_detections"] = stats.get("total_detections", 0)
        stats["inner_reported_ml_alerts_triggered"] = stats.get(
            "ml_alerts_triggered",
            0,
        )
        stats["total_detections"] = self._total_detections
        stats["ml_alerts_triggered"] = self._alerts_triggered
        stats["arbitration"] = self.arbitrator.get_stats()
        stats["layers"] = ["model_voting", "feature_arbitration"]
        return stats

    def _apply_arbitration(
        self,
        result: DetectionResult,
        decision: ArbitrationDecision | None,
    ) -> DetectionResult:
        if decision is None:
            return result
        triggered_models = self._triggered_models(result)
        requires_uncertainty_arbitration = bool(
            result.details.get("uncertainty_gate")
        )
        if (
            result.anomalous and not requires_uncertainty_arbitration
        ) or not triggered_models:
            return result

        details = dict(result.details)
        arbitration_details = decision.to_details()
        details.update(arbitration_details)
        details["arbitration"] = arbitration_details
        details["triggered_models"] = triggered_models
        details["trigger_model"] = triggered_models[0]

        if not decision.available:
            return replace(
                result,
                reason="feature arbitration window is not yet complete",
                details=details,
            )
        if decision.conclusion == "normal":
            return replace(result, details=details)

        exceeded = decision.exceeded_features
        confidence = min(1.0, len(exceeded) / 3.0)
        feature_summary = ", ".join(exceeded)
        conclusion = (
            "suspected"
            if requires_uncertainty_arbitration
            else decision.conclusion
        )
        level = "yellow" if requires_uncertainty_arbitration else decision.level
        details["final_conclusion"] = conclusion
        return replace(
            result,
            anomalous=True,
            score=confidence,
            confidence=confidence,
            reason=(
                f"feature arbitration {conclusion}: "
                f"{len(exceeded)} feature(s) exceeded threshold"
            ),
            level=level,
            source="ai_feature_arbitration",
            message=(
                f"[AI特征仲裁] {result.name} "
                f"{'确认异常' if conclusion == 'confirmed' else '疑似异常'} "
                f"(超限:{feature_summary})"
            ),
            details=details,
        )

    @staticmethod
    def _triggered_models(result: DetectionResult) -> list[str]:
        triggered_models = result.details.get("triggered_models", [])
        if isinstance(triggered_models, Sequence) and not isinstance(
            triggered_models,
            (str, bytes),
        ):
            if triggered_models:
                return [str(model_id) for model_id in triggered_models]

        model_results = result.details.get("model_results", {})
        if isinstance(model_results, Mapping):
            triggered = []
            for model_id, model_result in model_results.items():
                if not isinstance(model_result, Mapping):
                    continue
                vote = model_result.get("vote")
                if vote is True or (
                    vote is None and bool(model_result.get("raw_anomalous"))
                ):
                    triggered.append(str(model_id))
            return triggered

        votes = result.details.get("votes", {})
        if not isinstance(votes, Mapping):
            return []
        return [str(model_id) for model_id, vote in votes.items() if vote is True]


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _population_standard_deviation(
    values: Sequence[float],
    mean: float,
) -> float:
    variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(max(variance, 0.0))


def _linear_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2.0
    y_mean = _mean(values)
    numerator = math.fsum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(values)
    )
    denominator = math.fsum((index - x_mean) ** 2 for index in range(len(values)))
    return numerator / denominator


def _bounded(numerator: float, denominator: float) -> float:
    value = numerator / max(abs(denominator), 1e-12)
    return max(min(value, 1e6), -1e6)


def _variance_change(
    recent_standard_deviation: float,
    historical_standard_deviation: float,
    scale_floor: float,
) -> float:
    recent_variance = recent_standard_deviation**2
    historical_variance = historical_standard_deviation**2
    variance_floor = scale_floor**2
    if recent_variance <= variance_floor and historical_variance <= variance_floor:
        return 1.0
    ratio = recent_variance / max(historical_variance, variance_floor)
    return max(min(ratio, 1e6), 0.0)


def _direction(value: float) -> str:
    if value > 0:
        return "increase"
    if value < 0:
        return "decrease"
    return "stable"


def _feature_evidence(
    *,
    value: float,
    threshold: float,
    exceeded: bool,
    direction: str,
    raw_value: float | None = None,
    normalized_value: float | None = None,
) -> dict[str, Any]:
    evidence = {
        "value": _rounded(value),
        "threshold": float(threshold),
        "exceeded": bool(exceeded),
        "direction": direction,
    }
    if raw_value is not None:
        evidence["raw_value"] = _rounded(raw_value)
    if normalized_value is not None:
        evidence["normalized_value"] = _rounded(normalized_value)
    return evidence


def _rounded(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded
