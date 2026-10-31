"""
Custom data upload API.

JSON and CSV batches are validated completely before the engine is mutated, so a
malformed batch never leaves partial state behind.
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from app.dependencies import AppServices, get_services
from app.sensor_batch import SensorBatch
from app.ingestion import (
    IngestionValidationError,
    validate_csv_batch,
    validate_json_batch,
)

router = APIRouter()


def _process_records(
    services: AppServices,
    records: list[dict],
    *,
    live_eligible: bool,
):
    batch = SensorBatch(
        records=records,
        live_eligible=live_eligible,
    )
    with services.processing_lock:
        return services.processor.process(batch)


@router.post("/upload/csv")
async def upload_csv(
    file: UploadFile = File(...),
    push_live: bool = Query(default=True, description="Live Eligibility: 是否允许该批数据进入后续 1Hz Live Frame"),
    services: AppServices = Depends(get_services),
):
    """Upload a UTF-8 CSV file with the five required sensor fields."""
    content = await file.read()
    try:
        records = validate_csv_batch(content)
    except IngestionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = _process_records(services, records, live_eligible=push_live)

    return {
        "status": "ok",
        "records_ingested": len(records),
        "alerts_triggered": len(result.rule_alerts),
        "sensors_updated": services.engine.get_sensor_count(),
    }


@router.post("/upload/json")
async def upload_json(
    data: list[Any] = Body(..., description="传感器数据数组"),
    push_live: bool = Query(
        default=True,
        description="Live Eligibility: 是否允许该数据进入后续 1Hz Live Frame",
    ),
    services: AppServices = Depends(get_services),
):
    """Upload a JSON array containing at most 10,000 sensor readings."""
    try:
        records = validate_json_batch(data)
    except IngestionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = _process_records(services, records, live_eligible=push_live)

    return {
        "status": "ok",
        "records_ingested": len(records),
        "alerts_triggered": len(result.rule_alerts),
        "sensors_updated": services.engine.get_sensor_count(),
    }


@router.post("/upload/single")
async def push_single(
    sensor_id: str = Body(...),
    name: str = Body(...),
    type: str = Body(default="strain"),
    value: float = Body(...),
    push_live: bool = Query(
        default=True,
        description="Live Eligibility: 是否允许该数据进入后续 1Hz Live Frame",
    ),
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

    _process_records(services, records, live_eligible=push_live)
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
        with services.processing_lock:
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
