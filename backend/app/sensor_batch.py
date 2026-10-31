"""A sensor ingestion batch with its live-stream policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.sensor_reading import SensorReadingRecord


class LiveEligibility(StrEnum):
    BACKFILL = "backfill"
    INTERNAL = "internal"
    EXTERNAL = "external"

    @property
    def is_live(self) -> bool:
        return self is not LiveEligibility.BACKFILL

    @property
    def is_external(self) -> bool:
        return self is LiveEligibility.EXTERNAL


@dataclass(frozen=True, slots=True)
class SensorBatch:
    records: list[SensorReadingRecord]
    live_eligibility: LiveEligibility = LiveEligibility.INTERNAL
