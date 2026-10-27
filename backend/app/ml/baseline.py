"""Per-sensor normal baseline learning shared by detector implementations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from app.ml.contracts import BASELINE_READING_TARGET, BaselineStatus


@dataclass
class _BaselineAccumulator:
    sensor_id: str
    relearning: bool = False
    readings: int = 0
    mean: float = 0.0
    m2: float = 0.0
    ema_fast: float | None = None
    ema_slow: float | None = None
    ready: bool = False

    @property
    def std(self) -> float:
        return math.sqrt(self.m2 / self.readings) if self.readings else 0.0

    def observe(
        self,
        value: float,
        *,
        fast_alpha: float,
        slow_alpha: float,
    ) -> None:
        if self.ready:
            return

        self.readings += 1
        delta = value - self.mean
        self.mean += delta / self.readings
        self.m2 += delta * (value - self.mean)

        if self.ema_fast is None or self.ema_slow is None:
            self.ema_fast = value
            self.ema_slow = value
        else:
            self.ema_fast = fast_alpha * value + (1 - fast_alpha) * self.ema_fast
            self.ema_slow = slow_alpha * value + (1 - slow_alpha) * self.ema_slow

    def mark_ready(self) -> None:
        self.ready = True

    def status(self, required_readings: int) -> BaselineStatus:
        if self.ready:
            state = "ready"
        elif self.relearning:
            state = "relearning"
        else:
            state = "learning"
        return BaselineStatus(
            sensor_id=self.sensor_id,
            readings=self.readings,
            required_readings=required_readings,
            state=state,
            mean=round(self.mean, 6) if self.readings else None,
            std=round(self.std, 6) if self.readings else None,
            ema_fast=round(self.ema_fast, 6) if self.ema_fast is not None else None,
            ema_slow=round(self.ema_slow, 6) if self.ema_slow is not None else None,
        )


class BaselineLearner:
    """Accumulate the first configured number of normal readings per sensor."""

    def __init__(
        self,
        *,
        required_readings: int = BASELINE_READING_TARGET,
        fast_alpha: float = 0.3,
        slow_alpha: float = 0.05,
        known_sensor_ids: Iterable[str] = (),
    ) -> None:
        if required_readings <= 0:
            raise ValueError("required_readings must be positive")
        if not 0 < fast_alpha <= 1 or not 0 < slow_alpha <= 1:
            raise ValueError("EMA alpha values must be in (0, 1]")

        self.required_readings = required_readings
        self.fast_alpha = fast_alpha
        self.slow_alpha = slow_alpha
        self._accumulators: dict[str, _BaselineAccumulator] = {
            str(sensor_id): _BaselineAccumulator(sensor_id=str(sensor_id))
            for sensor_id in known_sensor_ids
        }

    def observe(
        self,
        sensor_id: str,
        value: float,
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        accumulator = self._get_or_create(str(sensor_id))
        if not is_normal or accumulator.ready:
            return accumulator.status(self.required_readings)

        accumulator.observe(
            float(value),
            fast_alpha=self.fast_alpha,
            slow_alpha=self.slow_alpha,
        )
        if accumulator.readings >= self.required_readings:
            accumulator.mark_ready()
        return accumulator.status(self.required_readings)

    def get_status(self, sensor_id: str) -> BaselineStatus:
        return self._get_or_create(str(sensor_id)).status(self.required_readings)

    def get_statuses(self) -> dict[str, BaselineStatus]:
        return {
            sensor_id: accumulator.status(self.required_readings)
            for sensor_id, accumulator in self._accumulators.items()
        }

    def reset(self, sensor_id: str | None = None) -> None:
        if sensor_id is None:
            for current_id in list(self._accumulators):
                self._accumulators[current_id] = _BaselineAccumulator(
                    sensor_id=current_id,
                    relearning=True,
                )
            return

        sensor_id = str(sensor_id)
        self._accumulators[sensor_id] = _BaselineAccumulator(
            sensor_id=sensor_id,
            relearning=self._accumulators.get(sensor_id, None) is not None,
        )

    def _get_or_create(self, sensor_id: str) -> _BaselineAccumulator:
        accumulator = self._accumulators.get(sensor_id)
        if accumulator is None:
            accumulator = _BaselineAccumulator(sensor_id=sensor_id)
            self._accumulators[sensor_id] = accumulator
        return accumulator
