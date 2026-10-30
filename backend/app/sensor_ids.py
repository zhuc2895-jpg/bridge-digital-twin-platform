"""Validated sensor identifier values."""

from typing import Self


class SensorIdentifier(str):
    """A normalized sensor identifier with string-compatible identity."""

    __slots__ = ()

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise ValueError("sensor_id must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("sensor_id is required")
        return super().__new__(cls, normalized)
