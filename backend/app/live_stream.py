"""Application-scoped live stream publishing and thread lifecycle."""

from __future__ import annotations

from collections.abc import Callable
import logging
import threading
import time

from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.live_contract import build_sensor_update, normalize_live_readings
from app.processing import SensorDataProcessor
from app.ws.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class SensorUpdatePublisher:
    """Build and enqueue sensor_update payloads through one policy boundary."""

    def __init__(
        self,
        engine: MonitoringEngine,
        ws_manager: WebSocketManager,
    ) -> None:
        self.engine = engine
        self.ws_manager = ws_manager

    def publish(self, *, queued_at: float | None = None) -> None:
        try:
            payload = build_sensor_update(self.engine)
            self.ws_manager.enqueue_broadcast(payload, queued_at=queued_at)
        except Exception:
            logger.exception("Failed to publish sensor_update; continuing live stream")


def process_live_tick(
    *,
    simulator: DataSimulator,
    processor: SensorDataProcessor,
    publisher: SensorUpdatePublisher,
    processing_lock: threading.RLock,
    generated_at: float,
) -> None:
    """Generate, ingest, and publish one serialized live frame."""
    try:
        raw_readings = simulator.next_readings()
    except Exception:
        logger.exception("Live simulator generation failed")
        raw_readings = []

    readings = normalize_live_readings(raw_readings)
    with processing_lock:
        try:
            processor.process(readings)
        except Exception:
            logger.exception("Live ingestion/detector pipeline failed")
        publisher.publish(queued_at=generated_at)


class LiveStreamRunner:
    """Own the one application-scoped live stream thread."""

    def __init__(
        self,
        process_tick: Callable[[float], None],
        interval_seconds: Callable[[], float],
        set_running: Callable[[bool], None],
    ) -> None:
        self._process_tick = process_tick
        self._interval_seconds = interval_seconds
        self._set_running = set_running
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
        self._set_running(True)
        next_tick = time.monotonic()
        try:
            while not self._stop_event.is_set():
                generated_at = time.monotonic()
                try:
                    self._process_tick(generated_at)
                except Exception:
                    logger.exception("Live tick failed; continuing with next frame")

                interval = max(float(self._interval_seconds()), 0.001)
                next_tick += interval
                now = time.monotonic()
                if next_tick <= now:
                    next_tick = now + interval
                self._stop_event.wait(next_tick - now)
        finally:
            self._set_running(False)
            with self._lifecycle_lock:
                if self._thread is threading.current_thread():
                    self._thread = None
