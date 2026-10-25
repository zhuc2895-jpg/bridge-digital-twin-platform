"""Application service assembly and FastAPI dependency providers."""

from dataclasses import dataclass

from fastapi import Depends, Request

from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.ml.anomaly_detector import AnomalyDetector
from app.ws.websocket_manager import WebSocketManager


@dataclass
class AppServices:
    """Mutable state owned by one application instance."""

    engine: MonitoringEngine
    simulator: DataSimulator
    detector: AnomalyDetector
    ws_manager: WebSocketManager


def create_services() -> AppServices:
    """Create a fresh, isolated set of services for an application instance."""
    return AppServices(
        engine=MonitoringEngine(),
        simulator=DataSimulator(),
        detector=AnomalyDetector(),
        ws_manager=WebSocketManager(),
    )


def get_services(request: Request) -> AppServices:
    return request.app.state.services


def get_engine(services: AppServices = Depends(get_services)) -> MonitoringEngine:
    return services.engine
