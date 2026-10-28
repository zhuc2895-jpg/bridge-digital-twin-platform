"""Per-sensor sliding-window Isolation Forest detector."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import math
from typing import Any, Mapping

from sklearn.ensemble import IsolationForest

from app.ml.baseline import BaselineLearner
from app.ml.contracts import BaseDetector, BaselineStatus, DetectionResult


@dataclass(frozen=True)
class _FittedModel:
    """A fitted forest plus the distribution used to calibrate its scores."""

    model: IsolationForest
    value_center: float
    value_scale: float
    decision_center: float
    decision_scale: float


@dataclass
class _SensorModelState:
    """Training state owned independently by one sensor."""

    window: deque[float]
    model: _FittedModel | None = None
    readings_since_refit: int = 0
    refit_pending: bool = False
    last_refit_error: str | None = None


class IsolationForestDetector(BaseDetector):
    """Detect values outside a calibrated rolling window for each sensor."""

    detector_id = "isolation_forest"
    display_name = "Isolation Forest"
    source = "ai_isolation_forest"

    def __init__(
        self,
        *,
        required_readings: int = 100,
        window_size: int = 200,
        min_readings: int = 50,
        score_threshold: float = 0.95,
        n_estimators: int = 100,
        contamination: str | float = "auto",
        random_state: int = 42,
        refit_interval: int = 25,
    ) -> None:
        if window_size <= 1:
            raise ValueError("window_size must be greater than one")
        if min_readings < 2 or min_readings > window_size:
            raise ValueError("min_readings must be between 2 and window_size")
        if not 0 <= score_threshold <= 1:
            raise ValueError("score_threshold must be between zero and one")
        if n_estimators <= 0:
            raise ValueError("n_estimators must be positive")
        if refit_interval <= 0:
            raise ValueError("refit_interval must be positive")
        if contamination != "auto" and not 0 < float(contamination) <= 0.5:
            raise ValueError("contamination must be 'auto' or in (0, 0.5]")

        self.window_size = window_size
        self.min_readings = min_readings
        self.score_threshold = float(score_threshold)
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.random_state = random_state
        self.refit_interval = refit_interval
        self._baselines = BaselineLearner(
            required_readings=max(required_readings, min_readings)
        )
        self._states: dict[str, _SensorModelState] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._total_detections = 0
        self._anomalies_detected = 0

    @property
    def parameters(self) -> dict[str, object]:
        return {
            "required_readings": self._baselines.required_readings,
            "window_size": self.window_size,
            "min_readings": self.min_readings,
            "score_threshold": self.score_threshold,
            "n_estimators": self.n_estimators,
            "contamination": self.contamination,
            "random_state": self.random_state,
            "refit_interval": self.refit_interval,
        }

    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        sensor_id = str(reading["sensor_id"])
        state = self._state_for(sensor_id)
        status = self._baselines.observe(
            sensor_id,
            float(reading["value"]),
            is_normal=is_normal,
        )
        if is_normal:
            state.window.append(float(reading["value"]))
        if (
            status.ready
            and state.model is None
            and len(state.window) >= self.min_readings
        ):
            self._fit_now(state)
        return status

    def get_baseline_status(
        self,
        sensor_id: str | None = None,
    ) -> BaselineStatus | dict[str, BaselineStatus]:
        if sensor_id is not None:
            return self._baselines.get_status(sensor_id)
        return self._baselines.get_statuses()

    def reset_baseline(self, sensor_id: str | None = None) -> None:
        self._baselines.reset(sensor_id)
        if sensor_id is None:
            self._states.clear()
            return
        self._states.pop(str(sensor_id), None)

    def detect_one(self, reading: Mapping[str, Any]) -> DetectionResult:
        sensor_id = str(reading["sensor_id"])
        value = float(reading["value"])
        status = self._baselines.get_status(sensor_id)
        state = self._state_for(sensor_id)
        self._total_detections += 1

        if not status.ready:
            return self.make_result(
                reading=reading,
                anomalous=False,
                score=0.0,
                confidence=0.0,
                reason=f"baseline_{status.state}",
                details={"vote": False, "baseline": status.to_dict()},
            )

        model = state.model
        if model is None:
            return self.make_result(
                reading=reading,
                anomalous=False,
                score=0.0,
                confidence=0.0,
                reason="isolation_forest_not_ready",
                details={
                    "vote": False,
                    "model_ready": False,
                    "training_readings": len(state.window),
                    "required_readings": self.min_readings,
                    "parameters": self.parameters,
                },
            )

        # decision_function units depend on the fitted forest, so calibrate
        # against the training decisions and retain a distribution-distance guard.
        decision: float | None
        value_deviation_sigma: float | None
        if model.value_scale <= 1e-12:
            relative_deviation = abs(value - model.value_center) / max(
                abs(model.value_center),
                1.0,
            )
            score = min(0.999, relative_deviation / 0.05)
            decision = None
            value_deviation_sigma = None
        else:
            decision = float(model.model.decision_function([[value]])[0])
            decision_z = (decision - model.decision_center) / max(
                model.decision_scale, 1e-12
            )
            value_deviation_sigma = abs(value - model.value_center) / model.value_scale
            forest_score = min(0.999, max(0.0, -decision_z / 5.0))
            distribution_score = min(
                0.999,
                max(0.0, (value_deviation_sigma - 2.0) / 4.0),
            )
            score = max(forest_score, distribution_score)
        confidence = score

        anomalous = score >= self.score_threshold
        if anomalous:
            self._anomalies_detected += 1
        else:
            self._record_normal_value(state, value)

        reason = (
            f"isolation score {score:.4f} reaches threshold "
            f"{self.score_threshold:.4f}"
            if anomalous
            else f"isolation score {score:.4f} is within threshold"
        )
        return self.make_result(
            reading=reading,
            anomalous=anomalous,
            score=round(score, 6),
            confidence=round(confidence, 6),
            reason=reason,
            details={
                "vote": anomalous,
                "model_ready": True,
                "decision_score": (
                    round(decision, 6) if decision is not None else None
                ),
                "decision_center": round(model.decision_center, 6),
                "decision_scale": round(model.decision_scale, 6),
                "value_deviation_sigma": (
                    round(value_deviation_sigma, 6)
                    if value_deviation_sigma is not None
                    else None
                ),
                "score_threshold": self.score_threshold,
                "training_readings": len(state.window),
                "parameters": self.parameters,
            },
        )

    def get_stats(self) -> dict:
        statuses = self._baselines.get_statuses()
        sensors = {}
        for sensor_id, status in statuses.items():
            state = self._states.get(sensor_id)
            sensors[sensor_id] = {
                "model_ready": state is not None and state.model is not None,
                "baseline_ready": status.ready,
                "readings": status.readings,
                "training_readings": len(state.window) if state is not None else 0,
                "refit_pending": state.refit_pending if state is not None else False,
                "last_refit_error": (
                    state.last_refit_error if state is not None else None
                ),
            }

        return {
            "total_detections": self._total_detections,
            "anomalies_detected": self._anomalies_detected,
            "baseline_readings": sum(status.readings for status in statuses.values()),
            "parameters": self.parameters,
            "sensors": sensors,
        }

    def _state_for(self, sensor_id: str) -> _SensorModelState:
        return self._states.setdefault(
            sensor_id,
            _SensorModelState(window=deque(maxlen=self.window_size)),
        )

    def _fit_now(self, state: _SensorModelState) -> None:
        state.model = self._fit_values([[value] for value in state.window])
        state.readings_since_refit = 0
        state.last_refit_error = None

    def _record_normal_value(self, state: _SensorModelState, value: float) -> None:
        state.window.append(value)
        state.readings_since_refit += 1
        if state.readings_since_refit >= self.refit_interval:
            self._schedule_refit(state)

    def _schedule_refit(self, state: _SensorModelState) -> None:
        if state.refit_pending or len(state.window) < self.min_readings:
            return
        state.refit_pending = True
        values = [[value] for value in state.window]
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="isolation-forest-refit",
            )
        self._executor.submit(self._refit, state, values)

    def _refit(
        self,
        state: _SensorModelState,
        values: list[list[float]],
    ) -> None:
        try:
            state.model = self._fit_values(values)
            state.readings_since_refit = 0
            state.last_refit_error = None
        except Exception as exc:  # background boundary must not terminate the worker
            state.last_refit_error = f"{type(exc).__name__}: {exc}"
        finally:
            state.refit_pending = False

    def _fit_values(self, values: list[list[float]]) -> _FittedModel:
        model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=1,
        )
        model.fit(values)
        flat_values = [current[0] for current in values]
        value_center = math.fsum(flat_values) / len(flat_values)
        value_variance = math.fsum(
            (current - value_center) ** 2 for current in flat_values
        ) / len(flat_values)
        decisions = model.decision_function(values)
        decision_center = math.fsum(decisions) / len(decisions)
        decision_variance = math.fsum(
            (current - decision_center) ** 2 for current in decisions
        ) / len(decisions)
        return _FittedModel(
            model=model,
            value_center=value_center,
            value_scale=math.sqrt(value_variance),
            decision_center=decision_center,
            decision_scale=max(math.sqrt(decision_variance), 1e-4),
        )
