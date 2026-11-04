"""Server-authored physical and connection state for sensor readings."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from app.sensor_metrics import finite_float, is_online, is_time_valid

PhysicalState = Literal["normal", "yellow", "orange", "red", "unknown"]
ConnectionState = Literal["online", "offline"]

UNKNOWN_PHYSICAL_STATE: PhysicalState = "unknown"
NORMAL_PHYSICAL_STATE: PhysicalState = "normal"
PHYSICAL_STATE_SEVERITY: dict[str, int] = {
    "unknown": -1,
    "normal": 0,
    "yellow": 1,
    "orange": 2,
    "red": 3,
}


def normalized_thresholds(
    thresholds: Mapping[str, float],
) -> tuple[float, float, float] | None:
    """Return validated yellow/orange/red bands, or None when incomplete."""
    yellow = finite_float(thresholds.get("yellow"))
    orange = finite_float(thresholds.get("orange"))
    red = finite_float(thresholds.get("red"))
    if yellow is None or orange is None or red is None:
        return None
    if yellow <= 0 or orange <= 0 or red <= 0:
        return None
    if not yellow < orange < red:
        return None
    return yellow, orange, red


def physical_state_for_reading(
    value: Any,
    thresholds: Mapping[str, float],
    *,
    timestamp: Any,
    reference_time: Any,
) -> PhysicalState:
    """Derive physical state from the active threshold profile."""
    if not is_time_valid(timestamp, reference_time):
        return UNKNOWN_PHYSICAL_STATE
    numeric_value = finite_float(value)
    bands = normalized_thresholds(thresholds)
    if numeric_value is None or bands is None:
        return UNKNOWN_PHYSICAL_STATE
    yellow, orange, red = bands
    magnitude = abs(numeric_value)
    if magnitude >= red:
        return "red"
    if magnitude >= orange:
        return "orange"
    if magnitude >= yellow:
        return "yellow"
    return NORMAL_PHYSICAL_STATE


def connection_state_for_reading(
    timestamp: Any,
    reference_time: Any,
) -> ConnectionState:
    return "online" if is_online(timestamp, reference_time) else "offline"


def project_sensor_state(
    *,
    value: Any,
    thresholds: Mapping[str, float],
    timestamp: Any,
    reference_time: Any,
) -> tuple[PhysicalState, ConnectionState]:
    """Return the two independent states carried by one projected reading."""
    return (
        physical_state_for_reading(
            value,
            thresholds,
            timestamp=timestamp,
            reference_time=reference_time,
        ),
        connection_state_for_reading(timestamp, reference_time),
    )


def normalized_response_ratio(
    value: Any,
    thresholds: Mapping[str, float],
) -> float:
    """Normalize a reading against the red band for the response field."""
    numeric_value = finite_float(value)
    bands = normalized_thresholds(thresholds)
    if numeric_value is None or bands is None:
        return 0.0
    return min(abs(numeric_value) / bands[2], 1.25)


def highest_physical_state(states: Iterable[str]) -> PhysicalState:
    """Return the highest known state, or unknown when nothing is known."""
    highest: PhysicalState = UNKNOWN_PHYSICAL_STATE
    highest_severity = -1
    for raw_state in states:
        state = str(raw_state)
        severity = PHYSICAL_STATE_SEVERITY.get(state, -1)
        if severity > highest_severity:
            highest = state
            highest_severity = severity
    return highest if highest_severity >= 0 else UNKNOWN_PHYSICAL_STATE
