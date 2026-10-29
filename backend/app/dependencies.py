"""Application service assembly and FastAPI dependency providers."""

from dataclasses import dataclass

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
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


def build_detector_registry() -> DetectorRegistry:
    """Assemble the detector plugins enabled at application startup."""
    return DetectorRegistry([VotingDetector()])


def create_services() -> AppServices:
    """Create a fresh, isolated set of services for an application instance."""
    engine = MonitoringEngine()
    detectors = DetectorManager(build_detector_registry())
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
