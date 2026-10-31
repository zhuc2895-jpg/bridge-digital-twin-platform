"""Bounded wire contracts and validation for the real-time sensor stream."""

from __future__ import annotations

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
    name_limit: int = 128,
) -> list[dict[str, Any]]:
    """Keep the latest reading per sensor with bounded wire payload size."""
    latest: dict[Any, dict[str, Any]] = {}
    for reading in readings:
        compact = _compact_reading(reading, name_limit=name_limit)
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

    # Keep the recent-20 alert contract intact. Compress dynamic text and trim
    # sensor records as needed, because an incomplete alert list is not a valid
    # sensor_update message.
    for sensor_name_limit, alert_name_limit, alert_message_limit in (
        (32, 16, 24),
        (8, 8, 8),
    ):
        sensors = _latest_sensor_readings(
            readings,
            name_limit=sensor_name_limit,
        )
        alerts = [
            _compact_alert(
                alert,
                sensor_id_limit=16,
                name_limit=alert_name_limit,
                message_limit=alert_message_limit,
            )
            for alert in alerts
        ]
        payload["sensors"] = sensors
        payload["alerts"] = alerts
        if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
            return payload

    while sensors and _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        sensors.pop(0)

    if _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        alerts = [
            _compact_alert(
                alert,
                sensor_id_limit=8,
                name_limit=0,
                message_limit=0,
            )
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
