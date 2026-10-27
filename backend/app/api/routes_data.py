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
    return engine.check_thresholds(records)


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
            "alerts": engine.get_recent_alerts(),
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
    temperature_yellow: Optional[float] = None,
    temperature_orange: Optional[float] = None,
    temperature_red: Optional[float] = None,
    services: AppServices = Depends(get_services),
):
    """Dynamically adjust physical thresholds for the current app instance."""
    requested = {
        "strain": {
            "yellow": strain_yellow,
            "orange": strain_orange,
            "red": strain_red,
        },
        "displacement": {
            "yellow": displacement_yellow,
            "orange": displacement_orange,
            "red": displacement_red,
        },
        "acceleration": {
            "yellow": acceleration_yellow,
            "orange": acceleration_orange,
            "red": acceleration_red,
        },
        "temperature": {
            "yellow": temperature_yellow,
            "orange": temperature_orange,
            "red": temperature_red,
        },
    }
    try:
        current_thresholds = services.engine.update_thresholds(requested)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updates = {
        f"{sensor_type}_{level}": value
        for sensor_type, levels in requested.items()
        for level, value in levels.items()
        if value is not None
    }
    return {
        "status": "ok",
        "updated": updates,
        "current_thresholds": current_thresholds,
    }


@router.get("/config/thresholds")
async def get_thresholds(services: AppServices = Depends(get_services)):
    """View the threshold configuration for the current app instance."""
    return services.engine.thresholds
