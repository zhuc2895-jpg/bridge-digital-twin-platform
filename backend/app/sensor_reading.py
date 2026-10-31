"""Typed transport record for one validated Sensor Reading."""

from __future__ import annotations

from typing import TypedDict

from app.sensor_ids import SensorIdentifier
from app.sensor_types import SensorType


class SensorReadingRecord(TypedDict):
    sensor_id: SensorIdentifier
    name: str
    type: SensorType
    value: float
    timestamp: float
