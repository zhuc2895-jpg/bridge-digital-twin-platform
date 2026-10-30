"""Application service assembly and FastAPI dependency providers."""

import threading
from dataclasses import dataclass, field

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.ml.contracts import ReadingPredicate
from app.ml.feature_arbitration import FeatureArbitrationDetector
from app.ml.registry import DetectorManager, DetectorRegistry
from app.ml.voting import VotingDetector
from app.processing import SensorDataProcessor
from app.ws.websocket_manager import WebSocketManager


@dataclass
class AppServices:
    """Mutable state owned by one application instance."""

    engine: MonitoringEngine
    simulator: DataSimulator
    detectors: DetectorManager
    processor: SensorDataProcessor
    ws_manager: WebSocketManager
    processing_lock: threading.RLock = field(default_factory=threading.RLock)

    async def broadcast_sensor_update(self, readings: list[dict]) -> None:
        await self.ws_manager.broadcast(
            {
                "type": "sensor_update",
                "sensors": readings,
                "alerts": self.engine.get_recent_alerts(),
                "stats": self.engine.get_stats(),
            }
        )


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
