"""STALWART-inspired fast/slow EMA anomaly detector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.ml.baseline import BaselineLearner
from app.ml.contracts import BaseDetector, BaselineStatus, DetectionResult


@dataclass
class _EMAState:
    fast: float
    slow: float


class StalwartDetector(BaseDetector):
    """Flag abrupt changes using divergence between fast and slow EMAs."""

    detector_id = "stalwart"
    display_name = "STALWART-inspired EMA"
    source = "ai_stalwart"

    def __init__(
        self,
        *,
        required_readings: int = 100,
        fast_alpha: float = 0.3,
        slow_alpha: float = 0.05,
        threshold_sigma: float = 3.0,
        min_std: float = 1e-6,
    ) -> None:
        if threshold_sigma <= 0:
            raise ValueError("threshold_sigma must be positive")
        if min_std <= 0:
            raise ValueError("min_std must be positive")

        self.fast_alpha = float(fast_alpha)
        self.slow_alpha = float(slow_alpha)
        self.threshold_sigma = float(threshold_sigma)
        self.min_std = float(min_std)
        self._baselines = BaselineLearner(
            required_readings=required_readings,
            fast_alpha=self.fast_alpha,
            slow_alpha=self.slow_alpha,
        )
        self._emas: dict[str, _EMAState] = {}
        self._total_detections = 0
        self._anomalies_detected = 0

    @property
    def parameters(self) -> dict[str, float | int]:
        return {
            "required_readings": self._baselines.required_readings,
            "fast_alpha": self.fast_alpha,
            "slow_alpha": self.slow_alpha,
            "threshold_sigma": self.threshold_sigma,
            "min_std": self.min_std,
        }

    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        sensor_id = str(reading["sensor_id"])
        status = self._baselines.observe(
            sensor_id,
            float(reading["value"]),
            is_normal=is_normal,
        )
        if status.ready and sensor_id not in self._emas:
            self._ema_for(sensor_id, status)
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
            self._emas.clear()
            return
        self._emas.pop(str(sensor_id), None)

    def detect_one(self, reading: Mapping[str, Any]) -> DetectionResult:
        sensor_id = str(reading["sensor_id"])
        value = float(reading["value"])
        status = self._baselines.get_status(sensor_id)
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

        state = self._emas.get(sensor_id)
        if state is None:
            state = self._ema_for(sensor_id, status)

        state.fast = self.fast_alpha * value + (1 - self.fast_alpha) * state.fast
        state.slow = self.slow_alpha * value + (1 - self.slow_alpha) * state.slow

        baseline_std = max(float(status.std or 0.0), self.min_std)
        deviation = abs(state.fast - state.slow)
        normalized_deviation = deviation / baseline_std
        anomalous = normalized_deviation > self.threshold_sigma
        score = min(1.0, normalized_deviation / (2 * self.threshold_sigma))
        confidence = min(1.0, normalized_deviation / self.threshold_sigma)
        if anomalous:
            self._anomalies_detected += 1

        reason = (
            f"fast/slow EMA deviation {normalized_deviation:.2f} sigma "
            f"exceeds {self.threshold_sigma:.2f} sigma"
            if anomalous
            else f"fast/slow EMA deviation {normalized_deviation:.2f} sigma is normal"
        )
        return self.make_result(
            reading=reading,
            anomalous=anomalous,
            score=round(score, 6),
            confidence=round(confidence, 6),
            reason=reason,
            details={
                "vote": anomalous,
                "fast_ema": round(state.fast, 6),
                "slow_ema": round(state.slow, 6),
                "ema_deviation": round(deviation, 6),
                "baseline_std": round(float(status.std or 0.0), 6),
                "normalized_deviation": round(normalized_deviation, 6),
                "threshold_sigma": self.threshold_sigma,
                "parameters": self.parameters,
            },
        )

    def get_stats(self) -> dict:
        statuses = self._baselines.get_statuses()
        return {
            "total_detections": self._total_detections,
            "anomalies_detected": self._anomalies_detected,
            "baseline_readings": sum(status.readings for status in statuses.values()),
            "parameters": self.parameters,
            "sensors": {
                sensor_id: {
                    "ready": status.ready,
                    "readings": status.readings,
                }
                for sensor_id, status in statuses.items()
            },
        }

    def _ema_for(self, sensor_id: str, status: BaselineStatus) -> _EMAState:
        seed = float(status.ema_fast or status.mean or 0.0)
        state = _EMAState(
            fast=seed,
            slow=float(status.ema_slow or seed),
        )
        self._emas[sensor_id] = state
        return state
