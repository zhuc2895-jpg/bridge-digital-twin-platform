"""End-to-end sensor processing with rule-first detector degradation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.engine.data_engine import Alert, MonitoringEngine
from app.ml.contracts import DetectionResult
from app.ml.registry import DetectorManager
from app.persistence import CheckpointManager
from app.sensor_batch import SensorBatch

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    rule_alerts: list[Alert] = field(default_factory=list)
    ai_alerts: list[Alert] = field(default_factory=list)
    detections: list[DetectionResult] = field(default_factory=list)


class SensorDataProcessor:
    """Persist readings, evaluate physical rules, then run AI detectors."""

    def __init__(
        self,
        engine: MonitoringEngine,
        detectors: DetectorManager,
        *,
        persistence: CheckpointManager | None = None,
    ) -> None:
        self.engine = engine
        self.detectors = detectors
        self.persistence = persistence

    def process(self, batch: SensorBatch) -> ProcessingResult:
        self.engine.ingest(batch)
        try:
            result = ProcessingResult(
                rule_alerts=self.engine.check_thresholds(batch)
            )

            try:
                detections = self.detectors.detect(
                    batch.records,
                    normal_predicate=self.engine.is_normal_reading,
                )
            except Exception:
                logger.exception("Detector pipeline failed; retaining rule alerts")
                return result

            result.detections = detections
            for detection in detections:
                try:
                    alert = self.engine.submit_alert(
                        sensor_id=detection.sensor_id,
                        sensor_name=detection.name,
                        level=detection.level or "yellow",
                        message=detection.message or detection.reason,
                        value=detection.value,
                        threshold=0.0,
                        source=detection.source or "ai_dual_confirm",
                        timestamp=detection.timestamp,
                        details=dict(detection.details),
                        live_eligible=batch.live_eligibility.is_live,
                    )
                except Exception:
                    logger.exception(
                        "Failed to submit detector result from %s",
                        detection.detector_id,
                    )
                    continue
                if alert is not None:
                    result.ai_alerts.append(alert)

            return result
        finally:
            if self.persistence is not None:
                self.persistence.commit()
