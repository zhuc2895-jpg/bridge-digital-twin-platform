"""Bounded wire contracts and validation for the real-time sensor stream."""

from __future__ import annotations

import logging
import math
from typing import Any

from app.engine.data_engine import MonitoringEngine
from app.sensor_ids import SensorIdentifier
from app.sensor_types import SensorType
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


def _truncate_text(value: Any, limit: int) -> str:
    return str(value)[:limit]


def _compact_reading(reading: dict[str, Any], name_limit: int = 128) -> dict[str, Any]:
    return {
        "sensor_id": _truncate_text(reading.get("sensor_id", ""), 64),
        "name": _truncate_text(reading.get("name", ""), name_limit),
        "type": _truncate_text(reading.get("type", "unknown"), 32),
        "value": reading.get("value"),
        "timestamp": reading.get("timestamp"),
    }


def _compact_alert(
    alert: dict[str, Any],
    *,
    sensor_id_limit: int = 64,
    name_limit: int = 128,
    message_limit: int = 512,
) -> dict[str, Any]:
    compact = {field: alert.get(field) for field in _ALERT_FIELDS}
    compact["sensor_id"] = _truncate_text(compact["sensor_id"] or "", sensor_id_limit)
    compact["sensor_name"] = _truncate_text(compact["sensor_name"] or "", name_limit)
    compact["message"] = _truncate_text(compact["message"] or "", message_limit)
    compact["level"] = _truncate_text(compact["level"] or "", 16)
    compact["source"] = _truncate_text(compact["source"] or "", 32)
    return compact


def _message_size(payload: dict[str, Any]) -> int:
    return len(WebSocketManager.encode(payload).encode("utf-8"))


def _latest_sensor_readings(
    readings: list[dict[str, Any]],
    *,
    limit: int = 256,
) -> list[dict[str, Any]]:
    """Keep the latest reading per sensor with bounded wire payload size."""
    latest: dict[Any, dict[str, Any]] = {}
    for reading in readings:
        compact = _compact_reading(reading)
        latest[compact["sensor_id"]] = compact
    return list(latest.values())[-limit:]


def build_sensor_update(
    engine: MonitoringEngine,
    readings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one bounded sensor_update payload shared by every recipient."""
    sensors = _latest_sensor_readings(readings)
    alerts = [_compact_alert(alert) for alert in engine.get_recent_alerts()[:20]]
    payload = {
        "type": "sensor_update",
        "sensors": sensors,
        "alerts": alerts,
        "stats": engine.get_stats(),
    }
    if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
        return payload

    # Preserve the complete sensor frame and all 20 alerts where possible, but
    # reduce dynamic text before dropping older alert records.
    alerts = [
        _compact_alert(
            alert,
            sensor_id_limit=24,
            name_limit=24,
            message_limit=32,
        )
        for alert in alerts
    ]
    payload["alerts"] = alerts
    while alerts and _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        alerts.pop()
    while sensors and _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        sensors.pop(0)
    if _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        payload["sensors"] = []
        payload["alerts"] = []
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
            if not isinstance(record, dict):
                raise ValueError("reading must be an object")
            reading_sensor_id = SensorIdentifier(record["sensor_id"])
            reading_name = str(record.get("name", ""))
            reading_type = SensorType(record["type"])
            reading_value = float(record["value"])
            reading_timestamp = float(record["timestamp"])
            if not all(
                math.isfinite(value)
                for value in (reading_value, reading_timestamp)
            ):
                raise ValueError("value and timestamp must be finite")
            reading = {
                "sensor_id": reading_sensor_id,
                "name": reading_name,
                "type": reading_type,
                "value": reading_value,
                "timestamp": reading_timestamp,
            }
        except Exception as exc:
            logger.warning(
                "Skipping invalid live reading index=%d sensor_id=%r error=%s",
                index,
                sensor_id,
                exc,
            )
            continue
        valid.append(reading)
    return valid
