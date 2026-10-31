"""Real-time stream lifecycle, publishing, and bounded wire contracts."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Any, Protocol

from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.ingestion import IngestionValidationError, validate_json_record
from app.processing import SensorDataProcessor
from app.ws.websocket_manager import (
    MAX_SENSOR_UPDATE_BYTES,
    MessageTooLargeError,
    WebSocketManager,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _PayloadTextLimits:
    sensor_name: int
    alert_sensor_id: int
    alert_name: int
    alert_message: int


_ROOMY_LIMITS = _PayloadTextLimits(128, 64, 128, 512)
_COMPACT_LIMITS = _PayloadTextLimits(32, 16, 16, 24)
_EMERGENCY_LIMITS = _PayloadTextLimits(8, 8, 8, 8)

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


class LiveStreamHost(Protocol):
    engine: MonitoringEngine
    simulator: DataSimulator
    processor: SensorDataProcessor
    ws_manager: WebSocketManager
    sensor_updates: SensorUpdatePublisher
    live_stream_interval_seconds: float
    processing_lock: Any


def _truncate_text(value: Any, limit: int) -> str:
    return str(value)[:limit]


def _compact_reading(
    reading: dict[str, Any],
    limits: _PayloadTextLimits = _ROOMY_LIMITS,
) -> dict[str, Any]:
    return {
        "sensor_id": _truncate_text(reading.get("sensor_id", ""), 64),
        "name": _truncate_text(reading.get("name", ""), limits.sensor_name),
        "type": _truncate_text(reading.get("type", "unknown"), 32),
        "value": reading.get("value"),
        "timestamp": reading.get("timestamp"),
    }


def _compact_alert(
    alert: dict[str, Any],
    limits: _PayloadTextLimits = _ROOMY_LIMITS,
) -> dict[str, Any]:
    compact = {field: alert.get(field) for field in _ALERT_FIELDS}
    compact["sensor_id"] = _truncate_text(
        compact["sensor_id"] or "",
        limits.alert_sensor_id,
    )
    compact["sensor_name"] = _truncate_text(
        compact["sensor_name"] or "",
        limits.alert_name,
    )
    compact["message"] = _truncate_text(
        compact["message"] or "",
        limits.alert_message,
    )
    compact["level"] = _truncate_text(compact["level"] or "", 16)
    compact["source"] = _truncate_text(compact["source"] or "", 32)
    return compact


def _message_size(payload: dict[str, Any]) -> int:
    return len(WebSocketManager.encode(payload).encode("utf-8"))


def _latest_sensor_readings(
    readings: list[dict[str, Any]],
    *,
    limit: int = 256,
    text_limits: _PayloadTextLimits = _ROOMY_LIMITS,
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
    for text_limits in (_COMPACT_LIMITS, _EMERGENCY_LIMITS):
        sensors = _latest_sensor_readings(
            readings,
            text_limits=text_limits,
        )
        alerts = [_compact_alert(alert, limits=text_limits) for alert in alerts]
        payload["sensors"] = sensors
        payload["alerts"] = alerts
        if _message_size(payload) <= MAX_SENSOR_UPDATE_BYTES:
            return payload

    while sensors and _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        sensors.pop(0)

    if _message_size(payload) > MAX_SENSOR_UPDATE_BYTES:
        emergency = _PayloadTextLimits(8, 8, 0, 0)
        alerts = [_compact_alert(alert, limits=emergency) for alert in alerts]
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


class SensorUpdatePublisher:
    """Build and enqueue sensor_update payloads through one policy boundary."""

    def __init__(
        self,
        engine: MonitoringEngine,
        ws_manager: WebSocketManager,
    ) -> None:
        self.engine = engine
        self.ws_manager = ws_manager

    def publish(
        self,
        readings: list[dict[str, Any]],
        *,
        queued_at: float | None = None,
    ) -> None:
        try:
            payload = build_sensor_update(self.engine, readings)
            self.ws_manager.enqueue_broadcast(payload, queued_at=queued_at)
        except MessageTooLargeError:
            logger.exception("Refusing to broadcast oversized sensor_update")


class LiveStreamRunner:
    """Own the one application-scoped simulation and ingestion loop."""

    def __init__(self, host: LiveStreamHost) -> None:
        self._host = host
        self._lifecycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                if not self._stop_event.is_set():
                    return

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lifecycle_lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                logger.error("Live stream did not stop before a restart was requested")
                return

            self._stop_event.clear()
            thread = threading.Thread(
                target=self._run,
                name="bridge-live-stream",
                daemon=True,
            )
            self._thread = thread
            thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _run(self) -> None:
        host = self._host
        simulator = host.simulator
        simulator.is_running = True
        next_tick = time.monotonic()
        try:
            while not self._stop_event.is_set():
                generated_at = time.monotonic()
                try:
                    raw_readings = simulator.next_readings()
                except Exception:
                    logger.exception("Live simulator generation failed")
                    raw_readings = []

                readings = normalize_live_readings(raw_readings)
                try:
                    with host.processing_lock:
                        host.processor.process(readings)
                except Exception:
                    logger.exception("Live ingestion/detector pipeline failed")

                host.sensor_updates.publish(readings, queued_at=generated_at)

                interval = max(float(host.live_stream_interval_seconds), 0.001)
                next_tick += interval
                now = time.monotonic()
                if next_tick <= now:
                    next_tick = now + interval
                self._stop_event.wait(next_tick - now)
        finally:
            simulator.is_running = False
            with self._lifecycle_lock:
                if self._thread is threading.current_thread():
                    self._thread = None
