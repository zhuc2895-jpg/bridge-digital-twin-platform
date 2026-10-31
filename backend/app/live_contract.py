"""Bounded wire contracts and validation for real-time sensor updates."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

from app.engine.data_engine import MonitoringEngine
from app.ingestion import IngestionValidationError, validate_json_record
from app.ws.websocket_manager import MAX_SENSOR_UPDATE_BYTES, WebSocketManager

logger = logging.getLogger(__name__)

_ALERT_FIELDS = (
    "id",
    "sensor_id",
    "sensor_name",
    "level",
    "message",
    "value",
    "threshold",
    "source",
    "timestamp",
)


@dataclass(frozen=True, slots=True)
class _WireTextLimits:
    sensor_name: int
    alert_sensor_id: int
    alert_name: int
    alert_message: int
    alert_details: int


# Policies are ordered from richest evidence to the smallest message that can
# still carry the complete recent-20 alert list.
_DEFAULT_TEXT_LIMITS = _WireTextLimits(
    sensor_name=128,
    alert_sensor_id=64,
    alert_name=128,
    alert_message=512,
    alert_details=8192,
)
_SHORT_TEXT_LIMITS = _WireTextLimits(
    sensor_name=32,
    alert_sensor_id=16,
    alert_name=16,
    alert_message=24,
    alert_details=1024,
)
_MINIMAL_TEXT_LIMITS = _WireTextLimits(
    sensor_name=8,
    alert_sensor_id=8,
    alert_name=8,
    alert_message=8,
    alert_details=256,
)
_LAST_RESORT_TEXT_LIMITS = _WireTextLimits(
    sensor_name=8,
    alert_sensor_id=8,
    alert_name=0,
    alert_message=0,
    alert_details=64,
)
_EMPTY_DETAILS_LIMITS = _WireTextLimits(
    sensor_name=8,
    alert_sensor_id=8,
    alert_name=0,
    alert_message=0,
    alert_details=0,
)


def _truncate_text(value: Any, limit: int) -> str:
    return str(value)[:limit]


def _compact_reading(
    reading: dict[str, Any],
    limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> dict[str, Any]:
    return {
        "sensor_id": _truncate_text(reading.get("sensor_id", ""), 64),
        "name": _truncate_text(reading.get("name", ""), limits.sensor_name),
        "type": _truncate_text(reading.get("type", "unknown"), 32),
        "value": reading.get("value"),
        "timestamp": reading.get("timestamp"),
    }


def _bounded_details(details: Any, limit: int) -> dict[str, Any]:
    normalized = dict(details or {})
    if limit <= 0:
        return {"_truncated": True}
    serialized = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) <= limit:
        return normalized
    return {
        "_truncated": True,
        "preview": serialized[:limit],
    }


def _alert_payload(
    alert: dict[str, Any],
    limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> dict[str, Any]:
    payload = {field: alert.get(field) for field in _ALERT_FIELDS}
    payload["details"] = _bounded_details(
        alert.get("details"),
        limits.alert_details,
    )
    return payload


def _compact_alert(
    alert: dict[str, Any],
    limits: _WireTextLimits,
) -> dict[str, Any]:
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


def _message_size(payload: dict[str, Any]) -> int:
    return len(WebSocketManager.encode(payload).encode("utf-8"))


def _latest_sensor_readings(
    readings: list[dict[str, Any]],
    *,
    limit: int = 256,
    text_limits: _WireTextLimits = _DEFAULT_TEXT_LIMITS,
) -> list[dict[str, Any]]:
    """Keep the latest reading per sensor with bounded wire payload size."""
    latest: dict[Any, dict[str, Any]] = {}
    for reading in readings:
        compact = _compact_reading(reading, limits=text_limits)
        latest[compact["sensor_id"]] = compact
    return list(latest.values())[-limit:]


def build_sensor_update(
    engine: MonitoringEngine,
    readings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one bounded sensor_update payload shared by every recipient."""
    sensors = _latest_sensor_readings(readings)
    alerts = [_alert_payload(alert) for alert in engine.get_recent_alerts()[:20]]
    payload = {
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
