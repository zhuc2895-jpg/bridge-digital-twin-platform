"""Application service assembly and FastAPI dependency providers."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.analysis_execution import AnalysisExecutor, ThreadedAnalysisExecutor
from app.bridge_models import BridgeModelStore
from app.bridge_scene_profile import BridgeSceneProfile, bundled_scene_profile
from app.config import AppConfig
from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.history_read import HistoryReadModel
from app.live_stream import LiveStreamRunner, LiveTickPipeline
from app.ml.compensation import (
    ResponseCompensationEstimator,
    default_calibration_dataset,
)
from app.ml.contracts import ReadingPredicate
from app.ml.feature_arbitration import FeatureArbitrationDetector, FeatureArbitrator
from app.ml.modal_inversion import ModalInversionModel, default_modal_dataset
from app.ml.registry import DetectorManager, DetectorRegistry
from app.ml.spatial_residual import SpatialResidualModel
from app.ml.voting import VotingDetector
from app.persistence import (
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
    config: AppConfig
    model_store: BridgeModelStore
    response_estimator: ResponseCompensationEstimator
    modal_model: ModalInversionModel
    analysis_executor: AnalysisExecutor = field(
        default_factory=ThreadedAnalysisExecutor
    )
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

    @property
    def scene_profile(self) -> BridgeSceneProfile:
        profile = self.model_store.active_profile()
        return profile if profile is not None else bundled_scene_profile()


def build_detector_registry(
    normal_predicate: ReadingPredicate | None = None,
    *,
    config: AppConfig,
) -> DetectorRegistry:
    """Assemble the detector plugins enabled at application startup."""
    return DetectorRegistry(
        [
            FeatureArbitrationDetector(
                VotingDetector(
                    confidence_threshold=config.ai_confidence_threshold,
                    min_votes=config.ai_min_votes,
                    cognition_threshold=config.cognition_threshold,
                    uncertainty_threshold=config.uncertainty_threshold,
                    gan_submodels=config.gan_submodels,
                ),
                arbitrator=FeatureArbitrator(
                    mean_shift_threshold=config.feature_mean_shift_threshold,
                    variance_change_threshold=(
                        config.feature_variance_change_threshold
                    ),
                    trend_slope_threshold=config.feature_trend_slope_threshold,
                    spatial_model=SpatialResidualModel(
                        min_training_snapshots=(
                            config.spatial_min_training_snapshots
                        ),
                        min_sensors=config.spatial_min_sensors,
                        residual_threshold=config.spatial_residual_threshold,
                        min_coherent_sensors=config.spatial_min_coherent_sensors,
                        alpha=config.spatial_alpha,
                        weights=config.spatial_weights,
                    ),
                ),
                normal_predicate=normal_predicate,
            )
        ]
    )


def create_services(
    *,
    checkpoint_path: str | Path | None = None,
    checkpoint_store: CheckpointStore | None = None,
    persistence_enabled: bool = False,
    config: AppConfig | None = None,
) -> AppServices:
    """Create a fresh, isolated set of services for an application instance."""
    resolved_config = config or AppConfig.from_env()
    engine = MonitoringEngine(
        thresholds=resolved_config.thresholds,
        sensor_thresholds=resolved_config.sensor_thresholds,
        threshold_provenance=resolved_config.threshold_provenance,
    )
    persistence = None
    persistence_requested = (
        checkpoint_store is not None
        or checkpoint_path is not None
        or persistence_enabled
    )
    if persistence_requested:
        store = checkpoint_store or JsonCheckpointStore(
            checkpoint_path or resolved_config.checkpoint_path
        )
        persistence = CheckpointManager(engine, store)
        persistence.restore()
    detectors = DetectorManager(
        build_detector_registry(
            normal_predicate=engine.is_normal_reading,
            config=resolved_config,
        )
    )
    calibration = default_calibration_dataset()
    response_estimator = ResponseCompensationEstimator(
        calibration.cases,
        version=calibration.version,
    )
    modal_model = ModalInversionModel(default_modal_dataset())
    return AppServices(
        engine=engine,
        simulator=DataSimulator(),
        detectors=detectors,
        processor=SensorDataProcessor(engine, detectors, persistence=persistence),
        ws_manager=WebSocketManager(),
        config=resolved_config,
        model_store=BridgeModelStore(resolved_config.model_dir),
        response_estimator=response_estimator,
        modal_model=modal_model,
        persistence=persistence,
        live_stream_interval_seconds=resolved_config.live_interval_seconds,
        live_stream_autostart=resolved_config.simulation_enabled,
    )


def get_services(connection: HTTPConnection) -> AppServices:
    return connection.app.state.services


def get_engine(services: AppServices = Depends(get_services)) -> MonitoringEngine:
    return services.engine


def get_history_read_model(
    services: AppServices = Depends(get_services),
) -> HistoryReadModel:
    return HistoryReadModel(services.engine, services.processing_lock)


def get_analysis_executor(
    services: AppServices = Depends(get_services),
) -> AnalysisExecutor:
    return services.analysis_executor
