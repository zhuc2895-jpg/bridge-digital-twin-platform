"""Application service assembly and FastAPI dependency providers."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.ml.contracts import ReadingPredicate
from app.ml.feature_arbitration import FeatureArbitrationDetector
from app.ml.registry import DetectorManager, DetectorRegistry
from app.ml.voting import VotingDetector
from app.live_stream import build_sensor_update, normalize_live_readings
from app.processing import SensorDataProcessor
from app.ws.websocket_manager import MessageTooLargeError, WebSocketManager

logger = logging.getLogger(__name__)


@dataclass
class AppServices:
    """Mutable state owned by one application instance."""

    engine: MonitoringEngine
    simulator: DataSimulator
    detectors: DetectorManager
    processor: SensorDataProcessor
    ws_manager: WebSocketManager
    live_stream_interval_seconds: float = 1.0
    live_stream_autostart: bool = True
    processing_lock: threading.RLock = field(default_factory=threading.RLock)
    _live_lifecycle_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )
    _live_stop_event: threading.Event = field(
        default_factory=threading.Event,
        init=False,
        repr=False,
    )
    _live_thread: threading.Thread | None = field(
        default=None,
        init=False,
        repr=False,
    )

    @property
    def is_live_stream_running(self) -> bool:
        thread = self._live_thread
        return thread is not None and thread.is_alive()

    async def broadcast_sensor_update(self, readings: list[dict]) -> None:
        payload = build_sensor_update(self.engine, readings)
        try:
            await self.ws_manager.broadcast(payload)
        except MessageTooLargeError:
            logger.exception("Refusing to broadcast oversized sensor_update")

    async def connect_live_client(self, websocket: Any) -> None:
        await self.ws_manager.connect(websocket)
        self.start_live_stream()

    def disconnect_live_client(self, websocket: Any) -> None:
        self.ws_manager.disconnect(websocket)

    def start_live_stream(self) -> None:
        with self._live_lifecycle_lock:
            thread = self._live_thread
            if thread is not None and thread.is_alive():
                if not self._live_stop_event.is_set():
                    return

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._live_lifecycle_lock:
            thread = self._live_thread
            if thread is not None and thread.is_alive():
                logger.error("Live stream did not stop before a restart was requested")
                return

            self._live_stop_event.clear()
            thread = threading.Thread(
                target=self._run_live_stream,
                name="bridge-live-stream",
                daemon=True,
            )
            self._live_thread = thread
            thread.start()

    def stop_live_stream(self) -> None:
        with self._live_lifecycle_lock:
            self._live_stop_event.set()
            thread = self._live_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _run_live_stream(self) -> None:
        simulator = self.simulator
        simulator.is_running = True
        next_tick = time.monotonic()
        try:
            while not self._live_stop_event.is_set():
                generated_at = time.monotonic()
                try:
                    raw_readings = simulator.next_readings()
                except Exception:
                    logger.exception("Live simulator generation failed")
                    raw_readings = []

                readings = normalize_live_readings(raw_readings)
                try:
                    with self.processing_lock:
                        self.processor.process(readings)
                except Exception:
                    logger.exception("Live ingestion/detector pipeline failed")

                try:
                    self.ws_manager.broadcast_now(
                        build_sensor_update(self.engine, readings),
                        queued_at=generated_at,
                    )
                except MessageTooLargeError:
                    logger.exception("Refusing to push oversized sensor_update")

                interval = max(float(self.live_stream_interval_seconds), 0.001)
                next_tick += interval
                now = time.monotonic()
                if next_tick <= now:
                    next_tick = now + interval
                self._live_stop_event.wait(next_tick - now)
        finally:
            simulator.is_running = False
            with self._live_lifecycle_lock:
                if self._live_thread is threading.current_thread():
                    self._live_thread = None


def build_detector_registry(
    normal_predicate: ReadingPredicate | None = None,
) -> DetectorRegistry:
    """Assemble the detector plugins enabled at application startup."""
    return DetectorRegistry(
        [
            FeatureArbitrationDetector(
                VotingDetector(),
                normal_predicate=normal_predicate,
            )
        ]
    )


def create_services() -> AppServices:
    """Create a fresh, isolated set of services for an application instance."""
    engine = MonitoringEngine()
    detectors = DetectorManager(
        build_detector_registry(normal_predicate=engine.is_normal_reading)
    )
    return AppServices(
        engine=engine,
        simulator=DataSimulator(),
        detectors=detectors,
        processor=SensorDataProcessor(engine, detectors),
        ws_manager=WebSocketManager(),
    )


def get_services(connection: HTTPConnection) -> AppServices:
    return connection.app.state.services


def get_engine(services: AppServices = Depends(get_services)) -> MonitoringEngine:
    return services.engine
