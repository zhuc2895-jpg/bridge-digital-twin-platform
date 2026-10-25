"""
Custom data upload API.

JSON and CSV batches are validated completely before the engine is mutated, so a
malformed batch never leaves partial state behind.
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from app.dependencies import AppServices, get_services
from app.engine.data_engine import MonitoringEngine
from app.ingestion import (
    IngestionValidationError,
    validate_csv_batch,
    validate_json_batch,
)

router = APIRouter()


def _ingest(records: list[dict], engine: MonitoringEngine):
    """Ingest validated records and persist the resulting rule alerts."""
    engine.ingest(records)
    alerts = engine.check_thresholds(records)
    for alert in alerts:
        engine.add_alert(alert)
    return alerts


async def _broadcast_update(
    services: AppServices,
    records: list[dict],
    push_live: bool,
) -> None:
    if not push_live:
        return
    engine = services.engine
    await services.ws_manager.broadcast(
        {
            "type": "sensor_update",
            "sensors": records,
            "alerts": engine.get_active_alerts(),
            "stats": engine.get_stats(),
        }
    )


@router.post("/upload/csv")
async def upload_csv(
    file: UploadFile = File(...),
    push_live: bool = Query(default=True, description="是否实时推送到前端"),
    services: AppServices = Depends(get_services),
):
    """Upload a UTF-8 CSV file with the five required sensor fields."""
    content = await file.read()
    try:
        records = validate_csv_batch(content)
    except IngestionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    alerts = _ingest(records, services.engine)
    await _broadcast_update(services, records, push_live)

    return {
        "status": "ok",
        "records_ingested": len(records),
        "alerts_triggered": len(alerts),
        "sensors_updated": services.engine.get_sensor_count(),
    }


@router.post("/upload/json")
async def upload_json(
    data: list[Any] = Body(..., description="传感器数据数组"),
    push_live: bool = Query(default=True),
    services: AppServices = Depends(get_services),
):
    """Upload a JSON array containing at most 10,000 sensor readings."""
    try:
        records = validate_json_batch(data)
    except IngestionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    alerts = _ingest(records, services.engine)
    await _broadcast_update(services, records, push_live)

    return {
        "status": "ok",
        "records_ingested": len(records),
        "alerts_triggered": len(alerts),
        "sensors_updated": services.engine.get_sensor_count(),
    }


@router.post("/upload/single")
async def push_single(
    sensor_id: str = Body(...),
    name: str = Body(...),
    type: str = Body(default="strain"),
    value: float = Body(...),
    push_live: bool = Query(default=True),
    services: AppServices = Depends(get_services),
):
    """Push one sensor reading for scripts, PLCs, or IoT devices."""
    import time

    raw_record = {
        "sensor_id": sensor_id,
        "name": name,
        "type": type,
        "value": value,
        "timestamp": time.time(),
    }
    try:
        records = validate_json_batch([raw_record])
    except IngestionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _ingest(records, services.engine)
    await _broadcast_update(services, records, push_live)
    return {"status": "ok", "sensor_id": sensor_id, "value": value}


@router.post("/config/thresholds")
async def update_thresholds(
    strain_yellow: Optional[float] = None,
    strain_orange: Optional[float] = None,
    strain_red: Optional[float] = None,
    displacement_yellow: Optional[float] = None,
    displacement_orange: Optional[float] = None,
    displacement_red: Optional[float] = None,
    acceleration_yellow: Optional[float] = None,
    acceleration_orange: Optional[float] = None,
    acceleration_red: Optional[float] = None,
    services: AppServices = Depends(get_services),
):
    """Dynamically adjust physical thresholds for the current app instance."""
    engine = services.engine
    updates = {}
    if strain_yellow is not None:
        engine.thresholds["strain"]["yellow"] = strain_yellow
        updates["strain_yellow"] = strain_yellow
    if strain_orange is not None:
        engine.thresholds["strain"]["orange"] = strain_orange
        updates["strain_orange"] = strain_orange
    if strain_red is not None:
        engine.thresholds["strain"]["red"] = strain_red
        updates["strain_red"] = strain_red
    if displacement_yellow is not None:
        engine.thresholds["displacement"]["yellow"] = displacement_yellow
        updates["displacement_yellow"] = displacement_yellow
    if displacement_orange is not None:
        engine.thresholds["displacement"]["orange"] = displacement_orange
        updates["displacement_orange"] = displacement_orange
    if displacement_red is not None:
        engine.thresholds["displacement"]["red"] = displacement_red
        updates["displacement_red"] = displacement_red
    if acceleration_yellow is not None:
        engine.thresholds["acceleration"]["yellow"] = acceleration_yellow
        updates["acceleration_yellow"] = acceleration_yellow
    if acceleration_orange is not None:
        engine.thresholds["acceleration"]["orange"] = acceleration_orange
        updates["acceleration_orange"] = acceleration_orange
    if acceleration_red is not None:
        engine.thresholds["acceleration"]["red"] = acceleration_red
        updates["acceleration_red"] = acceleration_red

    return {"status": "ok", "updated": updates, "current_thresholds": engine.thresholds}


@router.get("/config/thresholds")
async def get_thresholds(services: AppServices = Depends(get_services)):
    """View the threshold configuration for the current app instance."""
    return services.engine.thresholds
