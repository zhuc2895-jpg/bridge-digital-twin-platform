"""
数据分析 REST API
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.dependencies import AppServices, get_services
from app.engine.simulator import UnknownSimulatorSensorError
from app.html_report import render_monitoring_report
from app.ml.registry import DetectorRegistryError
from app.sensor_batch import LiveEligibility, SensorBatch
from app.sensor_ids import SensorIdentifier

router = APIRouter()


class AnomalyInjectionRequest(BaseModel):
    sensor_id: str


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
async def get_overview(services: AppServices = Depends(get_services)):
    """获取系统总览"""
    engine = services.engine
    detector = services.detectors
    simulator = services.simulator
    return {
        "engine": engine.get_stats(),
        "detector": detector.get_stats(),
        "simulator_running": simulator.is_running,
        "top_spikes": engine.get_top_spikes()
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
):
    """Start a fresh baseline for one sensor or every known sensor."""
    if sensor_id is not None and services.engine.get_latest(sensor_id) is None:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
    try:
        with services.processing_lock:
            return services.detectors.relearn(sensor_id)
    except DetectorRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/inject-anomaly")
async def inject_anomaly(
    payload: AnomalyInjectionRequest | None = Body(default=None),
    sensor_id: str | None = Query(default=None),
    services: AppServices = Depends(get_services),
):
    """Generate and process one injected reading for the requested sensor."""
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
async def get_top_spikes(services: AppServices = Depends(get_services)):
    """获取 Top-K 峰值"""
    engine = services.engine
    return engine.get_top_spikes()


@router.get("/report", response_class=HTMLResponse)
async def export_report(
    hours: int = Query(default=24, ge=1, le=168),
    title: str = Query(default="桥梁健康监测报告"),
    services: AppServices = Depends(get_services),
):
    """Export a printable HTML report for the requested trailing period."""
    return render_monitoring_report(services, hours=hours, title=title)
