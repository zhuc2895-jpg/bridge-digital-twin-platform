"""A sensor ingestion batch with its live-stream policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class SensorBatch:
    records: list[dict[str, Any]]
    live_eligible: bool = True

    @classmethod
    def coerce(
        cls,
        value: "SensorBatch | list[dict[str, Any]]",
        *,
        live_eligible: bool = True,
    ) -> "SensorBatch":
        if isinstance(value, cls):
            return value
        return cls(
            records=cast(list[dict[str, Any]], value),
            live_eligible=live_eligible,
        )
