"""Application service assembly and FastAPI dependency providers."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.live_stream import LiveStreamRunner, LiveTickPipeline
from app.ml.contracts import ReadingPredicate
from app.ml.feature_arbitration import FeatureArbitrationDetector
from app.ml.registry import DetectorManager, DetectorRegistry
from app.ml.voting import VotingDetector
from app.persistence import (
    DEFAULT_CHECKPOINT_PATH,
    CheckpointManager,
    CheckpointStore,
    JsonCheckpointStore,
)
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
    persistence: CheckpointManager | None = None
    live_stream_interval_seconds: float = 1.0
    live_stream_autostart: bool = True
    processing_lock: threading.RLock = field(default_factory=threading.RLock)
    live_tick: LiveTickPipeline = field(init=False)
    live_stream: LiveStreamRunner = field(init=False)

    def __post_init__(self) -> None:
        self.live_tick = LiveTickPipeline(environment=self)
        self.live_stream = LiveStreamRunner(
            process_tick=self.live_tick.run_once,
            interval_seconds=lambda: self.live_stream_interval_seconds,
            set_running=lambda running: setattr(
                self.simulator,
                "is_running",
                running,
            ),
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


def create_services(
    *,
    checkpoint_path: str | Path | None = None,
    checkpoint_store: CheckpointStore | None = None,
    persistence_enabled: bool = False,
) -> AppServices:
    """Create a fresh, isolated set of services for an application instance."""
    engine = MonitoringEngine()
    persistence = None
    if checkpoint_store is not None or checkpoint_path is not None or persistence_enabled:
        store = checkpoint_store or JsonCheckpointStore(
            checkpoint_path or DEFAULT_CHECKPOINT_PATH
        )
        persistence = CheckpointManager(engine, store)
        persistence.restore()
    detectors = DetectorManager(
        build_detector_registry(normal_predicate=engine.is_normal_reading)
    )
    return AppServices(
        engine=engine,
        simulator=DataSimulator(),
        detectors=detectors,
        processor=SensorDataProcessor(engine, detectors, persistence=persistence),
        ws_manager=WebSocketManager(),
        persistence=persistence,
    )


def get_services(connection: HTTPConnection) -> AppServices:
    return connection.app.state.services


def get_engine(services: AppServices = Depends(get_services)) -> MonitoringEngine:
    return services.engine
