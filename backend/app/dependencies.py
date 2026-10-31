"""Application service assembly and FastAPI dependency providers."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.live_stream import LiveStreamRunner, SensorUpdatePublisher
from app.ml.contracts import ReadingPredicate
from app.ml.feature_arbitration import FeatureArbitrationDetector
from app.ml.registry import DetectorManager, DetectorRegistry
from app.ml.voting import VotingDetector
from app.processing import SensorDataProcessor
from app.ws.websocket_manager import WebSocketManager


@dataclass
class AppServices:
    """Compose the mutable services owned by one application instance."""

    engine: MonitoringEngine
    simulator: DataSimulator
    detectors: DetectorManager
    processor: SensorDataProcessor
    ws_manager: WebSocketManager
    live_stream_interval_seconds: float = 1.0
    live_stream_autostart: bool = True
    processing_lock: threading.RLock = field(default_factory=threading.RLock)
    sensor_updates: SensorUpdatePublisher = field(init=False)
    live_stream: LiveStreamRunner = field(init=False)

    def __post_init__(self) -> None:
        self.sensor_updates = SensorUpdatePublisher(self.engine, self.ws_manager)
        self.live_stream = LiveStreamRunner(self)


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
