"""Closed vocabulary for supported sensor types."""

from enum import StrEnum


class SensorType(StrEnum):
    STRAIN = "strain"
    DISPLACEMENT = "displacement"
    ACCELERATION = "acceleration"
    TEMPERATURE = "temperature"
