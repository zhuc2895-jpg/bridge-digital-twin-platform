"""Validated sensor identifier values."""

from typing import Self

MAX_LIVE_SENSOR_ID_BYTES = 64


class SensorIdentifier(str):
    """A normalized sensor identifier with string-compatible identity."""

    __slots__ = ()

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise ValueError("sensor_id must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("sensor_id is required")
        try:
            normalized.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("sensor_id must be valid Unicode") from exc
        return super().__new__(cls, normalized)


def validate_live_sensor_identifier(
    sensor_id: SensorIdentifier,
) -> SensorIdentifier:
    """Enforce the identity bound required by Live Frame encoding."""
    encoded_bytes = len(sensor_id.encode("utf-8"))
    if encoded_bytes > MAX_LIVE_SENSOR_ID_BYTES:
        raise ValueError(
            f"sensor_id must be at most {MAX_LIVE_SENSOR_ID_BYTES} UTF-8 bytes "
            "for Live Eligible data"
        )
    return sensor_id
