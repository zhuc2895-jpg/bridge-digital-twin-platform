"""A sensor ingestion batch with its live-stream policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self


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
    records: list[dict[str, Any]]
    live_eligibility: LiveEligibility = LiveEligibility.INTERNAL

    @classmethod
    def from_records(
        cls,
        records: list[dict[str, Any]],
        live_eligibility: LiveEligibility = LiveEligibility.INTERNAL,
    ) -> Self:
        return cls(records=records, live_eligibility=live_eligibility)
