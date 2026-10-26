"""Shared sensor payload builders for backend tests."""

from collections.abc import Callable


def reading(
    sensor_id: str = "S01",
    name: str = "Main span strain",
    sensor_type: str = "strain",
    value: float = 100.0,
    timestamp: float = 1_700_000_000.0,
) -> dict:
    return {
        "sensor_id": sensor_id,
        "name": name,
        "type": sensor_type,
        "value": value,
        "timestamp": timestamp,
    }


def sensor_records(
    *,
    base: float,
    sensor_count: int,
    sample_count: int,
    sample_interval: float = 1.0,
    value_for: Callable[[int, int], float] | None = None,
) -> list[dict]:
    """Build ordered records for multiple sensors."""
    value_for = value_for or (lambda _sensor, index: float(index))
    return [
        reading(
            sensor_id=f"S{sensor}",
            name=f"Sensor {sensor}",
            value=value_for(sensor, index),
            timestamp=base + index * sample_interval,
        )
        for sensor in range(sensor_count)
        for index in range(sample_count)
    ]
