"""Shared sensor freshness and connectivity rules."""

from __future__ import annotations

import math
from typing import Any

ONLINE_SENSOR_FRESHNESS_SECONDS = 60.0


def finite_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def is_time_valid(timestamp: Any, reference_time: Any) -> bool:
    """Return whether a timestamp is not too far in the future."""
    parsed_timestamp = finite_float(timestamp)
    parsed_reference = finite_float(reference_time)
    if parsed_timestamp is None or parsed_reference is None:
        return False
    return parsed_timestamp <= parsed_reference + ONLINE_SENSOR_FRESHNESS_SECONDS


def is_online(timestamp: Any, reference_time: Any) -> bool:
    """Return whether a timestamp is within the inclusive freshness interval."""
    parsed_timestamp = finite_float(timestamp)
    parsed_reference = finite_float(reference_time)
    if parsed_timestamp is None or parsed_reference is None:
        return False
    return (
        parsed_reference - ONLINE_SENSOR_FRESHNESS_SECONDS
        <= parsed_timestamp
        <= parsed_reference + ONLINE_SENSOR_FRESHNESS_SECONDS
    )
