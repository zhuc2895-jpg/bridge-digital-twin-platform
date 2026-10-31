"""Bounded wire contracts and validation for real-time sensor updates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import logging
import math
from typing import Any, TypedDict

from app.engine.data_engine import MonitoringEngine
from app.ingestion import IngestionValidationError, validate_json_record
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
    type: str
    sensors: list[SensorReadingWire]
    alerts: list[AlertWire]
    stats: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _WireTextLimits:
    sensor_id: int
    sensor_name: int
    sensor_type: int
    alert_sensor_id: int
    alert_name: int
    alert_message: int


_DEFAULT_TEXT_LIMITS = _WireTextLimits(
    sensor_id=64,
    sensor_name=128,
    sensor_type=32,
    alert_sensor_id=64,
    alert_name=128,
    alert_message=512,
)
_SHORT_TEXT_LIMITS = _WireTextLimits(
    sensor_id=16,
    sensor_name=32,
    sensor_type=16,
    alert_sensor_id=16,
    alert_name=16,
    alert_message=24,
)
_MINIMAL_TEXT_LIMITS = _WireTextLimits(
    sensor_id=8,
    sensor_name=8,
    sensor_type=8,
    alert_sensor_id=8,
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


def _compact_reading(
    reading: Mapping[str, Any],
    limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> SensorReadingWire:
    return {
        "sensor_id": _truncate_text(
            reading.get("sensor_id", ""),
            limits.sensor_id,
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
    threshold, threshold_valid = _finite_number(alert.get("threshold", 0.0))
    timestamp, timestamp_valid = _finite_number(alert.get("timestamp", 0.0))
    invalid = not all((value_valid, threshold_valid, timestamp_valid))
    if invalid:
        logger.warning(
            "Sanitizing invalid sensor_update alert fields for %r",
            alert.get("sensor_id"),
        )
    return {
        "id": str(alert.get("id", "")),
        "sensor_id": _truncate_text(
            alert.get("sensor_id", ""),
            limits.alert_sensor_id,
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
        "source": _truncate_text(alert.get("source", ""), 32),
        "timestamp": timestamp,
        "invalid": invalid,
    }


def _message_size(payload: Mapping[str, Any]) -> int:
    return len(encode_message(payload).encode("utf-8"))


def _live_sensors(
    readings: list[dict[str, Any]],
    limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> list[SensorReadingWire]:
    return [_compact_reading(reading, limits) for reading in readings]


def build_sensor_update_from_snapshot(
    sensor_readings: list[dict[str, Any]],
    alert_records: list[dict[str, Any]],
    stats: dict[str, Any],
) -> SensorUpdateWire:
    """Build a bounded Live Frame from an already copied live snapshot."""
    sensors = _live_sensors(sensor_readings)
    alerts = [_alert_payload(alert) for alert in alert_records]
    payload: SensorUpdateWire = {
        "type": "sensor_update",
        "sensors": sensors,
        "alerts": alerts,
        "stats": stats,
    }
    if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
        return payload

    for text_limits in (_SHORT_TEXT_LIMITS, _MINIMAL_TEXT_LIMITS):
        sensors = _live_sensors(sensor_readings, text_limits)
        alerts = [_alert_payload(alert, text_limits) for alert in alert_records]
        payload["sensors"] = sensors
        payload["alerts"] = alerts
        if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
            return payload

    while sensors and _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        sensors.pop(0)

    payload["sensors"] = sensors
    return payload


def build_sensor_update(engine: MonitoringEngine) -> SensorUpdateWire:
    """Build one bounded Live Frame from current live-eligible state."""
    return build_sensor_update_from_snapshot(
        engine.get_live_snapshot(limit=32),
        engine.get_recent_live_alerts(),
        engine.get_stats(),
    )


def normalize_live_readings(records: Any) -> list[dict[str, Any]]:
    """Validate each live record independently so one bad item cannot stop a frame."""
    if not isinstance(records, list):
        logger.warning(
            "Live simulator returned %s instead of a reading list",
            type(records).__name__,
        )
        return []

    valid: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        sensor_id = record.get("sensor_id") if isinstance(record, dict) else None
        try:
            reading = validate_json_record(record, index)
        except (IngestionValidationError, OverflowError) as exc:
            logger.warning(
                "Skipping invalid live reading index=%d sensor_id=%r error=%s",
                index,
                sensor_id,
                exc,
            )
            continue
        valid.append(reading)
    return valid
