"""Bounded wire contracts and validation for real-time sensor updates."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.sensor_ids import MAX_LIVE_SENSOR_ID_BYTES
from app.ws.message_contract import MAX_SENSOR_UPDATE_BYTES, encode_message

logger = logging.getLogger(__name__)


class SensorReadingWire(TypedDict):
    sensor_id: str
    name: str
    type: str
    value: float
    timestamp: float


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


def build_sensor_update_from_snapshot(
    snapshot: LiveSensorSnapshot,
) -> SensorUpdateWire:
    """Build a bounded Live Frame from an already copied live snapshot."""
    sensors = _live_sensors(snapshot.sensors)
    alerts = [_alert_payload(alert) for alert in snapshot.alerts]
    payload: SensorUpdateWire = {
        "type": "sensor_update",
        "sensors": sensors,
        "alerts": alerts,
        "stats": snapshot.stats,
    }
    if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
        return payload

    for text_limits in (_SHORT_TEXT_LIMITS, _MINIMAL_TEXT_LIMITS):
        sensors = _live_sensors(snapshot.sensors, text_limits)
        alerts = [_alert_payload(alert, text_limits) for alert in snapshot.alerts]
        payload["sensors"] = sensors
        payload["alerts"] = alerts
        if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
            return payload

    while sensors and _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        sensors.pop()

    payload["sensors"] = sensors
    return payload
