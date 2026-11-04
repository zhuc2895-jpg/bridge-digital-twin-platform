"""Bounded wire contracts and validation for real-time sensor updates."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict, cast

from app.pressure_field import PressureUpdateWire
from app.sensor_ids import MAX_LIVE_SENSOR_ID_BYTES
from app.ws.message_contract import MAX_SENSOR_UPDATE_BYTES, encode_message

logger = logging.getLogger(__name__)


class SensorReadingWire(TypedDict):
    sensor_id: str
    name: str
    type: str
    value: float
    timestamp: float
    physical_state: str
    connection_state: str


class ThresholdProfileWire(TypedDict):
    version: str
    status: str


class FrameBudgetWire(TypedDict):
    limit_bytes: int
    omissions: list[str]
    text_detail: NotRequired[str]


class AlertWire(TypedDict):
    id: str
    sensor_id: str
    sensor_name: str
    level: str
    message: str
    value: float | None
    threshold: float | None
    source: str
    timestamp: float | None
    invalid: bool


class SensorUpdateWire(TypedDict):
    type: Literal["sensor_update"]
    sensors: list[SensorReadingWire]
    alerts: list[AlertWire]
    stats: dict[str, Any]
    budget: FrameBudgetWire
    threshold_profile: NotRequired[ThresholdProfileWire]
    pressure: NotRequired[PressureUpdateWire]


class AlertSnapshotRecord(TypedDict, total=False):
    id: str
    sensor_id: str
    sensor_name: str
    level: str
    message: str
    value: Any
    threshold: Any
    source: str
    timestamp: Any
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LiveSensorSnapshot:
    sensors: list[SensorReadingWire]
    alerts: list[AlertSnapshotRecord]
    stats: dict[str, Any]
    threshold_profile: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _WireTextLimits:
    sensor_id_bytes: int
    sensor_name: int
    sensor_type: int
    alert_sensor_id_bytes: int
    alert_name: int
    alert_message: int


_DEFAULT_TEXT_LIMITS = _WireTextLimits(
    sensor_id_bytes=MAX_LIVE_SENSOR_ID_BYTES,
    sensor_name=128,
    sensor_type=32,
    alert_sensor_id_bytes=MAX_LIVE_SENSOR_ID_BYTES,
    alert_name=128,
    alert_message=512,
)
_SHORT_TEXT_LIMITS = _WireTextLimits(
    sensor_id_bytes=MAX_LIVE_SENSOR_ID_BYTES,
    sensor_name=32,
    sensor_type=16,
    alert_sensor_id_bytes=MAX_LIVE_SENSOR_ID_BYTES,
    alert_name=16,
    alert_message=24,
)
_MINIMAL_TEXT_LIMITS = _WireTextLimits(
    sensor_id_bytes=MAX_LIVE_SENSOR_ID_BYTES,
    sensor_name=8,
    sensor_type=8,
    alert_sensor_id_bytes=MAX_LIVE_SENSOR_ID_BYTES,
    alert_name=8,
    alert_message=8,
)


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value)
    if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
        text = "".join(
            "\ufffd" if 0xD800 <= ord(character) <= 0xDFFF else character
            for character in text
        )
    return text[:limit]


def _identifier_text(value: Any, byte_limit: int) -> str:
    text = str(value)
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("sensor identifier must be valid Unicode") from exc
    if len(encoded) > byte_limit:
        raise ValueError(
            f"sensor identifier exceeds {byte_limit} UTF-8 bytes"
        )
    return text


def _compact_reading(
    reading: Mapping[str, Any],
    limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> SensorReadingWire:
    return {
        "sensor_id": _identifier_text(
            reading.get("sensor_id", ""),
            limits.sensor_id_bytes,
        ),
        "name": _truncate_text(reading.get("name", ""), limits.sensor_name),
        "type": _truncate_text(
            reading.get("type", "unknown"),
            limits.sensor_type,
        ),
        "value": float(reading.get("value", 0.0)),
        "timestamp": float(reading.get("timestamp", 0.0)),
        "physical_state": _truncate_text(
            reading.get("physical_state", "unknown"),
            16,
        ),
        "connection_state": _truncate_text(
            reading.get("connection_state", "offline"),
            16,
        ),
    }


def _finite_number(value: Any) -> tuple[float | None, bool]:
    if isinstance(value, bool):
        return None, False
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None, False
    if not math.isfinite(number):
        return None, False
    return number, True


def _alert_payload(
    alert: Mapping[str, Any],
    limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> AlertWire:
    value, value_valid = _finite_number(alert.get("value"))
    threshold, threshold_valid = _finite_number(alert.get("threshold"))
    source = _truncate_text(alert.get("source", ""), 32)
    if source == "rule":
        threshold_valid = (
            threshold_valid and threshold is not None and threshold > 0
        )
        if not threshold_valid:
            threshold = None
    elif threshold is not None and threshold <= 0:
        threshold = None
    timestamp, timestamp_valid = _finite_number(alert.get("timestamp"))
    invalid = not all((value_valid, threshold_valid, timestamp_valid))
    if invalid:
        logger.warning(
            "Sanitizing invalid sensor_update alert fields for %r",
            alert.get("sensor_id"),
        )
    return {
        "id": str(alert.get("id", "")),
        "sensor_id": _identifier_text(
            alert.get("sensor_id", ""),
            limits.alert_sensor_id_bytes,
        ),
        "sensor_name": _truncate_text(
            alert.get("sensor_name", ""),
            limits.alert_name,
        ),
        "level": _truncate_text(alert.get("level", ""), 16),
        "message": _truncate_text(
            alert.get("message", ""),
            limits.alert_message,
        ),
        "value": value,
        "threshold": threshold,
        "source": source,
        "timestamp": timestamp,
        "invalid": invalid,
    }


def _message_size(payload: Mapping[str, Any]) -> int:
    return len(encode_message(payload).encode("utf-8"))


def _live_sensors(
    readings: Sequence[Mapping[str, Any]],
    limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> list[SensorReadingWire]:
    return [_compact_reading(reading, limits) for reading in readings]


class LiveFrameBudgetError(ValueError):
    """No valid Live Frame can fit inside the configured byte budget."""


def _compact_pressure_payload(
    pressure: PressureUpdateWire,
) -> PressureUpdateWire | None:
    if not pressure.get("points"):
        return None
    compact = cast(PressureUpdateWire, dict(pressure))
    compact["points"] = []
    return compact


class LiveFrameAssembler:
    """Own Live Frame packaging, degradation order, and omission metadata."""

    def __init__(self, max_bytes: int | None = None) -> None:
        resolved_limit = MAX_SENSOR_UPDATE_BYTES if max_bytes is None else max_bytes
        if resolved_limit <= 0:
            raise ValueError("Live Frame byte budget must be positive")
        self.max_bytes = int(resolved_limit)

    def assemble(
        self,
        snapshot: LiveSensorSnapshot,
        *,
        pressure: PressureUpdateWire | None = None,
        pressure_omission: str | None = None,
    ) -> SensorUpdateWire:
        omissions: tuple[str, ...] = (
            (pressure_omission,)
            if pressure_omission
            else ()
        )
        payload = self._payload(
            snapshot,
            pressure=pressure,
            omissions=omissions,
        )
        if self._fits(payload):
            return payload

        if pressure is not None:
            compact_pressure = _compact_pressure_payload(pressure)
            if compact_pressure is not None:
                payload = self._payload(
                    snapshot,
                    pressure=compact_pressure,
                    omissions=("pressure.points",),
                )
                if self._fits(payload):
                    return payload
            omissions = ("pressure",)
            payload = self._payload(
                snapshot,
                pressure=None,
                omissions=omissions,
            )
            if self._fits(payload):
                return payload

        for text_detail, text_limits in (
            ("compact", _SHORT_TEXT_LIMITS),
            ("minimal", _MINIMAL_TEXT_LIMITS),
        ):
            payload = self._payload(
                snapshot,
                pressure=None,
                limits=text_limits,
                omissions=omissions,
                text_detail=text_detail,
            )
            if self._fits(payload):
                return payload

        sensors = _live_sensors(snapshot.sensors, _MINIMAL_TEXT_LIMITS)
        while sensors:
            sensors.pop()
            payload = self._payload(
                snapshot,
                pressure=None,
                limits=_MINIMAL_TEXT_LIMITS,
                omissions=(*omissions, "sensors"),
                text_detail="minimal",
                sensors=sensors,
            )
            if self._fits(payload):
                return payload

        raise LiveFrameBudgetError(
            f"Live Frame cannot fit within {self.max_bytes} bytes"
        )

    def _fits(self, payload: Mapping[str, Any]) -> bool:
        return _message_size(payload) <= self.max_bytes

    def _payload(
        self,
        snapshot: LiveSensorSnapshot,
        *,
        pressure: PressureUpdateWire | None,
        limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
        omissions: tuple[str, ...] = (),
        text_detail: str = "full",
        sensors: Sequence[SensorReadingWire] | None = None,
    ) -> SensorUpdateWire:
        payload: SensorUpdateWire = {
            "type": "sensor_update",
            "sensors": (
                list(sensors)
                if sensors is not None
                else _live_sensors(snapshot.sensors, limits)
            ),
            "alerts": [
                _alert_payload(alert, limits)
                for alert in snapshot.alerts
            ],
            "stats": snapshot.stats,
            "budget": {
                "limit_bytes": self.max_bytes,
                "omissions": list(omissions),
            },
        }
        if text_detail != "full":
            payload["budget"]["text_detail"] = text_detail
        if snapshot.threshold_profile:
            payload["threshold_profile"] = {
                "version": _truncate_text(
                    snapshot.threshold_profile.get("version", ""),
                    64,
                ),
                "status": _truncate_text(
                    snapshot.threshold_profile.get("status", ""),
                    16,
                ),
            }
        if pressure is not None:
            payload["pressure"] = pressure
        return payload


def build_sensor_update_from_snapshot(
    snapshot: LiveSensorSnapshot,
    *,
    pressure: PressureUpdateWire | None = None,
    pressure_omission: str | None = None,
) -> SensorUpdateWire:
    """Build a bounded Live Frame through the shared assembler policy."""
    return LiveFrameAssembler().assemble(
        snapshot,
        pressure=pressure,
        pressure_omission=pressure_omission,
    )
