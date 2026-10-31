"""Bounded wire contracts and validation for real-time sensor updates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
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
    value: float
    threshold: float
    source: str
    timestamp: float
    details: dict[str, Any]


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
    alert_details: int


# Policies are ordered from richest evidence to the smallest message that can
# still carry the complete recent-20 alert list.
_DEFAULT_TEXT_LIMITS = _WireTextLimits(
    sensor_id=64,
    sensor_name=128,
    sensor_type=32,
    alert_sensor_id=64,
    alert_name=128,
    alert_message=512,
    alert_details=8192,
)
_SHORT_TEXT_LIMITS = _WireTextLimits(
    sensor_id=16,
    sensor_name=32,
    sensor_type=16,
    alert_sensor_id=16,
    alert_name=16,
    alert_message=24,
    alert_details=1024,
)
_MINIMAL_TEXT_LIMITS = _WireTextLimits(
    sensor_id=8,
    sensor_name=8,
    sensor_type=8,
    alert_sensor_id=8,
    alert_name=8,
    alert_message=8,
    alert_details=256,
)
_LAST_RESORT_TEXT_LIMITS = _WireTextLimits(
    sensor_id=8,
    sensor_name=8,
    sensor_type=8,
    alert_sensor_id=8,
    alert_name=0,
    alert_message=0,
    alert_details=64,
)
_EMPTY_DETAILS_LIMITS = _WireTextLimits(
    sensor_id=8,
    sensor_name=8,
    sensor_type=8,
    alert_sensor_id=8,
    alert_name=0,
    alert_message=0,
    alert_details=0,
)


def _truncate_text(value: Any, limit: int) -> str:
    return str(value)[:limit]


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


def _json_default(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    return str(value)


def _bounded_details(details: Any, limit: int) -> dict[str, Any]:
    if limit <= 0:
        return {"_truncated": True}
    try:
        normalized = dict(details or {})
        serialized = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
            allow_nan=False,
        )
    except Exception:
        try:
            preview = str(details)[:limit]
        except Exception:
            preview = "<unserializable>"
        return {"_truncated": True, "preview": preview}
    if len(serialized) <= limit:
        decoded = json.loads(serialized)
        if decoded != normalized:
            decoded["_truncated"] = True
        return decoded
    return {
        "_truncated": True,
        "preview": serialized[:limit],
    }


def _finite_number(value: Any) -> tuple[float, bool]:
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return 0.0, False
    if not math.isfinite(number):
        return 0.0, False
    return number, True


def _alert_payload(
    alert: Mapping[str, Any],
    limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> AlertWire:
    value, value_valid = _finite_number(alert.get("value", 0.0))
    threshold, threshold_valid = _finite_number(alert.get("threshold", 0.0))
    timestamp, timestamp_valid = _finite_number(alert.get("timestamp", 0.0))
    invalid_fields = [
        field
        for field, valid in (
            ("value", value_valid),
            ("threshold", threshold_valid),
            ("timestamp", timestamp_valid),
        )
        if not valid
    ]
    details = _bounded_details(
        alert.get("details"),
        limits.alert_details,
    )
    if invalid_fields:
        details["_invalid_fields"] = invalid_fields
        logger.warning(
            "Sanitizing invalid sensor_update alert fields: %s",
            ", ".join(invalid_fields),
        )
    return {
        "id": str(alert.get("id", "")),
        "sensor_id": str(alert.get("sensor_id", "")),
        "sensor_name": str(alert.get("sensor_name", "")),
        "level": str(alert.get("level", "")),
        "message": str(alert.get("message", "")),
        "value": value,
        "threshold": threshold,
        "source": str(alert.get("source", "")),
        "timestamp": timestamp,
        "details": details,
    }


def _compact_alert(
    alert: Mapping[str, Any],
    limits: _WireTextLimits,
) -> AlertWire:
    payload = _alert_payload(alert, limits)
    payload["sensor_id"] = _truncate_text(
        payload["sensor_id"] or "",
        limits.alert_sensor_id,
    )
    payload["sensor_name"] = _truncate_text(
        payload["sensor_name"] or "",
        limits.alert_name,
    )
    payload["message"] = _truncate_text(
        payload["message"] or "",
        limits.alert_message,
    )
    payload["level"] = _truncate_text(payload["level"] or "", 16)
    payload["source"] = _truncate_text(payload["source"] or "", 32)
    return payload


def _message_size(payload: Mapping[str, Any]) -> int:
    return len(encode_message(payload).encode("utf-8"))


def _latest_sensor_readings(
    readings: list[dict[str, Any]],
    *,
    limit: int = 256,
    text_limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> list[SensorReadingWire]:
    """Keep the latest reading per sensor with bounded wire payload size."""
    latest: dict[Any, SensorReadingWire] = {}
    for reading in readings:
        compact = _compact_reading(reading, limits=text_limits)
        latest[compact["sensor_id"]] = compact
    return list(latest.values())[-limit:]


def build_sensor_update(
    engine: MonitoringEngine,
    readings: list[dict[str, Any]],
) -> SensorUpdateWire:
    """Build one bounded sensor_update payload shared by every recipient."""
    sensors = _latest_sensor_readings(readings)
    alerts = [_alert_payload(alert) for alert in engine.get_recent_alerts()[:20]]
    payload: SensorUpdateWire = {
        "type": "sensor_update",
        "sensors": sensors,
        "alerts": alerts,
        "stats": engine.get_stats(),
    }
    if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
        return payload

    for text_limits in (
        _SHORT_TEXT_LIMITS,
        _MINIMAL_TEXT_LIMITS,
        _LAST_RESORT_TEXT_LIMITS,
    ):
        sensors = _latest_sensor_readings(
            readings,
            text_limits=text_limits,
        )
        alerts = [_compact_alert(alert, text_limits) for alert in alerts]
        payload["sensors"] = sensors
        payload["alerts"] = alerts
        if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
            return payload

    while sensors and _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        sensors.pop(0)

    if _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        alerts = [
            _compact_alert(alert, _EMPTY_DETAILS_LIMITS)
            for alert in alerts
        ]
        payload["alerts"] = alerts
    return payload


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
