"""End-to-end sensor processing with rule-first detector degradation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.engine.data_engine import Alert, MonitoringEngine
from app.ml.contracts import DetectionResult
from app.ml.registry import DetectorManager

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
    ) -> None:
        self.engine = engine
        self.detectors = detectors

    def process(
        self,
        records: list[dict],
        *,
        live_eligible: bool = True,
    ) -> ProcessingResult:
        self.engine.ingest(records, live_eligible=live_eligible)
        result = ProcessingResult(
            rule_alerts=self.engine.check_thresholds(
                records,
                live_eligible=live_eligible,
            )
        )

        try:
            detections = self.detectors.detect(
                records,
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
                    live_eligible=live_eligible,
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
