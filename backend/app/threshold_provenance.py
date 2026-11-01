"""Threshold provenance and unit metadata for physical alert profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

THRESHOLD_UNITS = {
    "strain": "microstrain (µε)",
    "displacement": "millimetres (mm)",
    "acceleration": "metres per second squared (m/s²)",
    "temperature": "degrees Celsius (°C)",
}

_AUTHORITATIVE_FIELDS = (
    "source_document",
    "source_version",
    "source_section",
    "effective_date",
    "approved_by",
)


@dataclass(frozen=True, slots=True)
class ThresholdProvenance:
    """Source metadata for one threshold profile."""

    status: str = "provisional"
    profile_version: str = "provisional-default-v1"
    source_document: str | None = None
    source_version: str | None = None
    source_section: str | None = None
    effective_date: str | None = None
    approved_by: str | None = None
    scope: str = "all sensors of the same type"
    units: Mapping[str, str] = field(
        default_factory=lambda: dict(THRESHOLD_UNITS)
    )
    notes: str = (
        "Provisional engineering defaults; not an authoritative SRS or "
        "bridge-design limit."
    )

    def __post_init__(self) -> None:
        status = str(self.status).strip().lower()
        if status not in {"provisional", "authoritative"}:
            raise ValueError("threshold provenance status is invalid")
        profile_version = str(self.profile_version).strip()
        if not profile_version:
            raise ValueError("threshold profile_version is required")
        units = {
            str(sensor_type): str(unit).strip()
            for sensor_type, unit in self.units.items()
        }
        if set(units) != set(THRESHOLD_UNITS) or not all(units.values()):
            raise ValueError("threshold units must cover all sensor types")

        if status == "authoritative":
            missing = [
                name
                for name in _AUTHORITATIVE_FIELDS
                if not str(getattr(self, name) or "").strip()
            ]
            if missing:
                raise ValueError(
                    "authoritative threshold provenance is missing: "
                    + ", ".join(missing)
                )
            try:
                date.fromisoformat(str(self.effective_date))
            except ValueError as exc:
                raise ValueError(
                    "authoritative effective_date must be ISO YYYY-MM-DD"
                ) from exc

        object.__setattr__(self, "status", status)
        object.__setattr__(self, "profile_version", profile_version)
        object.__setattr__(self, "units", units)
        object.__setattr__(self, "scope", str(self.scope).strip())
        object.__setattr__(self, "notes", str(self.notes).strip())

    @property
    def authoritative(self) -> bool:
        return self.status == "authoritative"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "authoritative": self.authoritative,
            "profile_version": self.profile_version,
            "source_document": self.source_document,
            "source_version": self.source_version,
            "source_section": self.source_section,
            "effective_date": self.effective_date,
            "approved_by": self.approved_by,
            "scope": self.scope,
            "units": dict(self.units),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ThresholdProvenance:
        if not isinstance(value, Mapping):
            raise ValueError("threshold provenance must be a mapping")
        return cls(
            status=str(value.get("status", "provisional")),
            profile_version=str(
                value.get("profile_version", "provisional-default-v1")
            ),
            source_document=_optional_text(value.get("source_document")),
            source_version=_optional_text(value.get("source_version")),
            source_section=_optional_text(value.get("source_section")),
            effective_date=_optional_text(value.get("effective_date")),
            approved_by=_optional_text(value.get("approved_by")),
            scope=str(value.get("scope", "all sensors of the same type")),
            units=value.get("units", THRESHOLD_UNITS),
            notes=str(
                value.get(
                    "notes",
                    "Provisional engineering defaults; not an authoritative "
                    "SRS or bridge-design limit.",
                )
            ),
        )


def provisional_threshold_provenance() -> ThresholdProvenance:
    return ThresholdProvenance()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
