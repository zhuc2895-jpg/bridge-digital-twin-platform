"""Threshold provenance and unit metadata for physical alert profiles."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
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
    "scope",
    "effective_date",
    "approved_by",
)

DEFAULT_SENSOR_THRESHOLD_TYPES = {
    "S01": "strain",
    "S02": "strain",
    "S03": "displacement",
    "S04": "acceleration",
    "S05": "displacement",
    "S06": "strain",
    "S07": "acceleration",
    "S08": "temperature",
}


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
    scope: str = ""
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
        scope = str(self.scope or "").strip()
        if not scope:
            scope = (
                "provisional engineering defaults for all sensors of the same type"
                if status == "provisional"
                else ""
            )
        object.__setattr__(self, "scope", scope)
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
            scope=_optional_text(value.get("scope")) or "",
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


def default_threshold_profile_document() -> ThresholdProfileDocument:
    """Return the code-derived project profile pending engineering sign-off."""
    return ThresholdProfileDocument(
        thresholds={
            "strain": {"yellow": 960.0, "orange": 1200.0, "red": 1440.0},
            "displacement": {"yellow": 240.0, "orange": 300.0, "red": 360.0},
            "acceleration": {"yellow": 0.315, "orange": 0.50, "red": 0.80},
            "temperature": {"yellow": 46.0, "orange": 55.2, "red": 60.0},
        },
        sensor_thresholds={
            "S01": {"yellow": 960.0, "orange": 1200.0, "red": 1440.0},
            "S02": {"yellow": 720.0, "orange": 900.0, "red": 1080.0},
            "S03": {"yellow": 40.0, "orange": 50.0, "red": 60.0},
            "S04": {"yellow": 0.98, "orange": 2.94, "red": 4.41},
            "S05": {"yellow": 240.0, "orange": 300.0, "red": 360.0},
            "S06": {"yellow": 520.0, "orange": 650.0, "red": 780.0},
            "S07": {"yellow": 0.98, "orange": 2.94, "red": 4.41},
            "S08": {"yellow": 46.0, "orange": 55.2, "red": 60.0},
        },
        provenance=ThresholdProvenance(
            status="provisional",
            profile_version="code-derived-v1-pending-signoff",
            source_document=(
                "JT/T 1037-2022 公路桥梁结构监测技术规范; "
                "SJG 148-2024 桥梁结构健康监测技术标准; "
                "JTG/T 3365-01-2020 公路斜拉桥设计规范; "
                "JTG D60-2015 公路桥涵设计通用规范"
            ),
            source_version=(
                "JT/T 1037-2022 (2022-01-13发布, 2022-04-13实施); "
                "SJG 148-2024 (2024-01-12发布, 2024-05-01实施); "
                "JTG/T 3365-01-2020; JTG D60-2015"
            ),
            source_section=(
                "JT/T 1037-2022 第11章 表9/表10; SJG 148-2024 §8.3 "
                "表8.3.5/表8.3.6; JTG/T 3365-01-2020 §7.2.5; "
                "JTG D60-2015 §4.3.12 表4.3.12-2"
            ),
            effective_date=None,
            approved_by=None,
            scope=(
                "S01-S08 simulated cable-stayed bridge (main span L=120 m); "
                "per-measurement values in sensor_thresholds"
            ),
            notes=(
                "Code-derived values pending engineering sign-off. Yellow=0.8x "
                "design (strain yellow proxies the historical-maximum rule until "
                "monitoring history exists), orange=1.0x design, red=1.2x design; "
                "red for strain/temperature/cable acceleration is a platform "
                "extrapolation (codes define no third level there). Cable "
                "acceleration follows SJG 148-2024 Table 8.3.6 (100 mg / 300 mg). "
                "S08 red = 60 °C paving-layer alarm limit (JT/T 1037-2022 Table 9). "
                "Becomes authoritative only after approved_by and effective_date "
                "are signed."
            ),
        ),
    )


def default_threshold_provenance() -> ThresholdProvenance:
    return default_threshold_profile_document().provenance


@dataclass(frozen=True, slots=True)
class ThresholdProfileDocument:
    """One file containing both physical values and their provenance."""

    thresholds: dict[str, dict[str, float]]
    provenance: ThresholdProvenance
    sensor_thresholds: dict[str, dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "thresholds",
            _validate_profile_thresholds(self.thresholds),
        )
        if not isinstance(self.provenance, ThresholdProvenance):
            raise ValueError("threshold profile provenance is invalid")
        object.__setattr__(
            self,
            "sensor_thresholds",
            validate_sensor_thresholds(self.sensor_thresholds),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "thresholds": {
                sensor_type: dict(levels)
                for sensor_type, levels in self.thresholds.items()
            },
            "provenance": self.provenance.to_dict(),
            "sensor_thresholds": {
                sensor_id: dict(levels)
                for sensor_id, levels in self.sensor_thresholds.items()
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ThresholdProfileDocument:
        if not isinstance(value, Mapping):
            raise ValueError("threshold profile document must be an object")
        thresholds = value.get("thresholds")
        provenance = value.get("provenance")
        sensor_thresholds = value.get("sensor_thresholds", {})
        if not isinstance(thresholds, Mapping):
            raise ValueError("threshold profile document is missing thresholds")
        if not isinstance(provenance, Mapping):
            raise ValueError("threshold profile document is missing provenance")
        if not isinstance(sensor_thresholds, Mapping):
            raise ValueError("sensor_thresholds must be an object")
        return cls(
            thresholds=_validate_profile_thresholds(thresholds),
            provenance=ThresholdProvenance.from_dict(provenance),
            sensor_thresholds=validate_sensor_thresholds(sensor_thresholds),
        )

    @classmethod
    def load(cls, path: str | Path) -> ThresholdProfileDocument:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load threshold profile document: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("threshold profile document must be an object")
        return cls.from_dict(payload)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _validate_profile_thresholds(
    value: Mapping[str, Any],
) -> dict[str, dict[str, float]]:
    if not isinstance(value, Mapping):
        raise ValueError("threshold profile values must be a mapping")
    result: dict[str, dict[str, float]] = {}
    for sensor_type, levels in value.items():
        if str(sensor_type) not in THRESHOLD_UNITS or not isinstance(levels, Mapping):
            raise ValueError("threshold profile has an invalid sensor type")
        profile: dict[str, float] = {}
        for level in ("yellow", "orange", "red"):
            try:
                threshold = float(levels[level])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"threshold profile is missing {sensor_type}.{level}"
                ) from exc
            if not math.isfinite(threshold) or threshold <= 0:
                raise ValueError("threshold profile values must be positive and finite")
            profile[level] = threshold
        if not profile["yellow"] < profile["orange"] < profile["red"]:
            raise ValueError("threshold profile levels must be strictly ordered")
        result[str(sensor_type)] = profile
    if set(result) != set(THRESHOLD_UNITS):
        raise ValueError("threshold profile must cover all sensor types")
    return result


def validate_sensor_thresholds(
    value: Mapping[str, Any] | None,
) -> dict[str, dict[str, float]]:
    if not value:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("sensor_thresholds must be a mapping")
    result: dict[str, dict[str, float]] = {}
    for raw_sensor_id, levels in value.items():
        sensor_id = str(raw_sensor_id).strip()
        if not sensor_id or not isinstance(levels, Mapping):
            raise ValueError("sensor_thresholds has an invalid sensor entry")
        profile: dict[str, float] = {}
        for level in ("yellow", "orange", "red"):
            try:
                threshold = float(levels[level])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"sensor threshold is missing {sensor_id}.{level}"
                ) from exc
            if not math.isfinite(threshold) or threshold <= 0:
                raise ValueError("sensor thresholds must be positive and finite")
            profile[level] = threshold
        if not profile["yellow"] < profile["orange"] < profile["red"]:
            raise ValueError("sensor threshold levels must be strictly ordered")
        result[sensor_id] = profile
    return result


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
