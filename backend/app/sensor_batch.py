"""A sensor ingestion batch with its live-stream policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class SensorBatch:
    records: list[dict[str, Any]]
    live_eligible: bool = True
    live_override: bool = False

    @classmethod
    def coerce(
        cls,
        value: "SensorBatch | list[dict[str, Any]]",
        *,
        live_eligible: bool = True,
        live_override: bool = False,
    ) -> "SensorBatch":
        if isinstance(value, cls):
            return value
        return cls(
            records=cast(list[dict[str, Any]], value),
            live_eligible=live_eligible,
            live_override=live_override,
        )
