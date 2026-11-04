"""
数据分析 REST API
"""

import time

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.dependencies import AppServices, get_history_read_model, get_services
from app.engine.simulator import UnknownSimulatorSensorError
from app.history_read import HistoryReadError, HistoryReadModel
from app.html_report import render_monitoring_report
from app.ml.registry import DetectorRegistryError, DetectorRelearnError
from app.pressure_field import build_pressure_update
from app.sensor_batch import LiveEligibility, SensorBatch
from app.sensor_ids import SensorIdentifier

router = APIRouter()


class AnomalyInjectionRequest(BaseModel):
    sensor_id: str


class ResponseEstimateRequest(BaseModel):
    features: dict[str, float]
    sensor_id: str | None = None
    condition: str | None = None


class DeformationInversionRequest(BaseModel):
    timestamp: float | None = None
    measurements: dict[str, dict[str, float]] | None = None
    snr: dict[str, dict[str, float]] | None = None
    confidence: dict[str, dict[str, float]] | None = None


def _resolve_anomaly_target(
    payload: AnomalyInjectionRequest | None,
    sensor_id: str | None,
) -> SensorIdentifier:
    raw_sensor_ids = [
        payload.sensor_id if payload is not None else None,
        sensor_id,
    ]
    try:
        targets = [
            SensorIdentifier(raw_sensor_id)
            for raw_sensor_id in raw_sensor_ids
            if raw_sensor_id is not None
        ]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not targets:
        raise HTTPException(status_code=400, detail="sensor_id is required")
    if len(set(targets)) != 1:
        raise HTTPException(
            status_code=400,
            detail="body and query sensor_id values must match",
        )
    return targets[0]


@router.get("/overview")
async def get_overview(
    services: AppServices = Depends(get_services),
    history: HistoryReadModel = Depends(get_history_read_model),
):
    """获取系统总览"""
    engine = services.engine
    detector = services.detectors
    simulator = services.simulator
    return {
        "engine": engine.get_stats(),
        "detector": detector.get_stats(),
        "simulator_running": (
            simulator.is_running if services.config.simulation_enabled else False
        ),
        "top_spikes": history.top_spikes()
    }


@router.get("/detectors")
async def get_detector_status(
    services: AppServices = Depends(get_services),
):
    """Return detector health, baseline readiness, and learning reading counts."""
    return services.detectors.get_stats()


@router.post("/detectors/relearn")
async def relearn_detector_baselines(
    sensor_id: str | None = Query(default=None),
    services: AppServices = Depends(get_services),
    history: HistoryReadModel = Depends(get_history_read_model),
):
    """Start a fresh baseline for one sensor or every known sensor."""
    if sensor_id is not None and history.latest(sensor_id) is None:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
    try:
        with services.processing_lock:
            return services.detectors.relearn(sensor_id)
    except DetectorRelearnError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "failed_detectors": exc.detector_ids,
            },
        ) from exc
    except DetectorRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/inject-anomaly")
async def inject_anomaly(
    payload: AnomalyInjectionRequest | None = Body(default=None),
    sensor_id: str | None = Query(default=None),
    services: AppServices = Depends(get_services),
):
    """Generate and process one injected reading for the requested sensor."""
    if not services.config.simulation_enabled:
        raise HTTPException(
            status_code=503,
            detail="Simulation is disabled by configuration",
        )
    target = _resolve_anomaly_target(payload, sensor_id)
    simulator = services.simulator
    try:
        with services.processing_lock:
            generated = simulator.inject_anomaly(target)
            injected_readings = [generated.reading.to_dict()]
            services.processor.process(
                SensorBatch(
                    records=injected_readings,
                    live_eligibility=LiveEligibility.EXTERNAL,
                )
            )
    except UnknownSimulatorSensorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    injection = generated.injection
    injected_sensor_id = str(injection.sensor_id)
    return {
        "status": "injected",
        "sensor_id": injected_sensor_id,
        "pending_injections": 0,
        "injection": {
            "multiplier": injection.multiplier,
            "offset": injection.offset,
        },
        "message": f"已生成并处理传感器 {injected_sensor_id} 的下一条注入读数",
    }


@router.get("/top-spikes")
async def get_top_spikes(
    history: HistoryReadModel = Depends(get_history_read_model),
):
    """获取 Top-K 峰值"""
    return history.top_spikes()


@router.post("/response-estimate")
async def estimate_structural_response(
    payload: ResponseEstimateRequest,
    services: AppServices = Depends(get_services),
):
    """Estimate response through simulation prior plus measurement compensation."""
    estimate = await services.analysis_executor.run(
        services.response_estimator.estimate,
        payload.features,
    )
    return {
        "status": "estimated" if estimate.prediction is not None else "fallback",
        "sensor_id": payload.sensor_id,
        "condition": payload.condition,
        **estimate.to_dict(),
    }


@router.post("/deformation-inversion")
async def invert_full_field_deformation(
    payload: DeformationInversionRequest,
    services: AppServices = Depends(get_services),
    history: HistoryReadModel = Depends(get_history_read_model),
):
    """Invert modal coordinates and return the associated full-field deformation."""
    timestamp = payload.timestamp
    measurements = payload.measurements
    snapshot = None
    try:
        if timestamp is not None:
            snapshot = history.snapshot_at_retained_time(timestamp)
        elif measurements is None:
            timestamp, snapshot = history.latest_retained_snapshot()
    except HistoryReadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source = "measurements"
    if measurements is None:
        assert snapshot is not None
        primary_direction = services.modal_model.primary_direction
        measurements = {
            sensor_id: {primary_direction: float(reading["value"])}
            for sensor_id, reading in snapshot.items()
        }
        source = "snapshot"

    result = await services.analysis_executor.run(
        services.modal_model.invert,
        measurements,
        snr=payload.snr,
        confidence=payload.confidence,
    )
    return {
        "status": "ok" if result.available else "unavailable",
        "source": source,
        "timestamp": timestamp,
        "snapshot": snapshot,
        **result.to_dict(),
    }


@router.get("/response-field")
async def get_response_field(
    timestamp: float | None = Query(default=None),
    services: AppServices = Depends(get_services),
    history: HistoryReadModel = Depends(get_history_read_model),
):
    """Return the normalized response pressure field for a live or historical point."""
    engine = services.engine
    source = "live"
    resolved_timestamp = time.time()

    profile = services.scene_profile
    if timestamp is None:
        sensors = history.live_snapshot(limit=32)
    else:
        try:
            snapshot = history.snapshot_at_retained_time(timestamp)
        except HistoryReadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        sensors = list(snapshot.values())
        source = "history"
        resolved_timestamp = timestamp

    field = await services.analysis_executor.run(
        build_pressure_update,
        sensors,
        engine.projection_thresholds_for,
        deck_bounds=profile.deck_bounds.to_dict(),
        sensor_anchors={
            sensor_id: anchor.position
            for sensor_id, anchor in profile.sensor_anchors.items()
        },
        generated_at=resolved_timestamp,
    )
    threshold_profile = history.threshold_profile_summary()

    return {
        "status": "ok" if field["coverage"] else "unavailable",
        "source": source,
        "timestamp": resolved_timestamp,
        "threshold_profile": threshold_profile,
        **field,
    }


@router.get("/report", response_class=HTMLResponse)
async def export_report(
    hours: int = Query(default=24, ge=1, le=168),
    title: str = Query(default="桥梁健康监测报告"),
    services: AppServices = Depends(get_services),
):
    """Export a printable HTML report for the requested trailing period."""
    return await services.analysis_executor.run(
        render_monitoring_report,
        services,
        hours=hours,
        title=title,
    )
