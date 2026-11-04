"""Real-time structural response pressure fields built from sensor readings.

The field is a normalized response index, not a physical pressure measurement.
Each sensor contributes its absolute reading divided by its red threshold, and
the values are interpolated over the bridge deck plane with inverse-distance
weighting. This keeps the display useful when sensor types report in different
physical units while preserving the engineering threshold semantics.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, TypedDict

from app.sensor_state import highest_physical_state, normalized_response_ratio

PRESSURE_SCHEMA_VERSION = 1
PRESSURE_GRID_X = 25
PRESSURE_GRID_Z = 9


class PressureGridWire(TypedDict):
    nx: int
    nz: int
    x_min: float
    x_max: float
    z_min: float
    z_max: float


class PressurePointWire(TypedDict):
    sensor_id: str
    x: float
    z: float
    ratio: float
    value: float
    physical_state: str


class PressureUpdateWire(TypedDict):
    type: Literal["pressure_update"]
    version: int
    generated_at: float
    unit: str
    metric: str
    grid: PressureGridWire
    values: list[float]
    max: float
    max_level: str
    max_sensor_id: str | None
    coverage: int
    points: list[PressurePointWire]


ThresholdLookup = Callable[[str, str], Mapping[str, float]]


def _finite(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _interpolate(
    x: float,
    z: float,
    points: Sequence[tuple[float, float, float]],
) -> float:
    if not points:
        return 0.0
    weighted = 0.0
    weight_sum = 0.0
    for sensor_x, sensor_z, ratio in points:
        dx = x - sensor_x
        dz = z - sensor_z
        weight = 1.0 / (dx * dx + dz * dz + 25.0)
        weighted += ratio * weight
        weight_sum += weight
    return weighted / weight_sum if weight_sum else 0.0


def build_pressure_update(
    sensors: Sequence[Mapping[str, Any]],
    threshold_lookup: ThresholdLookup,
    *,
    deck_bounds: Mapping[str, float],
    sensor_anchors: Mapping[str, Sequence[float]],
    generated_at: float | None = None,
) -> PressureUpdateWire:
    """Build one semantic pressure field from live sensor readings."""
    x_min = _finite(deck_bounds.get("min_x"), -60.0)
    x_max = _finite(deck_bounds.get("max_x"), 60.0)
    z_min = _finite(deck_bounds.get("min_z"), -10.0)
    z_max = _finite(deck_bounds.get("max_z"), 10.0)
    if not x_min < x_max or not z_min < z_max:
        raise ValueError("pressure deck bounds are invalid")
    center_x = (x_min + x_max) / 2
    center_z = (z_min + z_max) / 2
    points: list[PressurePointWire] = []
    interpolation_points: list[tuple[float, float, float]] = []
    physical_states: list[str] = []
    max_ratio = 0.0
    max_sensor_id: str | None = None

    for reading in sensors:
        sensor_id = str(reading.get("sensor_id", ""))
        sensor_type = str(reading.get("type", "unknown"))
        value = _finite(reading.get("value"))
        thresholds = threshold_lookup(sensor_id, sensor_type)
        ratio = normalized_response_ratio(value, thresholds)
        physical_state = str(reading.get("physical_state", "unknown"))
        anchor = sensor_anchors.get(sensor_id)
        x = _finite(anchor[0], center_x) if anchor and len(anchor) >= 3 else center_x
        z = _finite(anchor[2], center_z) if anchor and len(anchor) >= 3 else center_z
        points.append(
            {
                "sensor_id": sensor_id,
                "x": round(x, 2),
                "z": round(z, 2),
                "ratio": round(ratio, 4),
                "value": round(value, 4),
                "physical_state": physical_state,
            }
        )
        physical_states.append(physical_state)
        interpolation_points.append((x, z, ratio))
        if ratio > max_ratio:
            max_ratio = ratio
            max_sensor_id = sensor_id

    values: list[float] = []
    for z_index in range(PRESSURE_GRID_Z):
        z = z_min + (
            (z_max - z_min)
            * z_index
            / (PRESSURE_GRID_Z - 1)
        )
        for x_index in range(PRESSURE_GRID_X):
            x = x_min + (
                (x_max - x_min)
                * x_index
                / (PRESSURE_GRID_X - 1)
            )
            values.append(round(_interpolate(x, z, interpolation_points), 3))

    payload: PressureUpdateWire = {
        "type": "pressure_update",
        "version": PRESSURE_SCHEMA_VERSION,
        "generated_at": round(time.time() if generated_at is None else generated_at, 3),
        "unit": "normalized_response",
        "metric": "abs(value) / red_threshold",
        "grid": {
            "nx": PRESSURE_GRID_X,
            "nz": PRESSURE_GRID_Z,
            "x_min": x_min,
            "x_max": x_max,
            "z_min": z_min,
            "z_max": z_max,
        },
        "values": values,
        "max": round(max_ratio, 4),
        "max_level": highest_physical_state(physical_states),
        "max_sensor_id": max_sensor_id,
        "coverage": len(points),
        "points": points,
    }
    return payload
