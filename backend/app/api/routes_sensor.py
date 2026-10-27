"""
传感器数据 REST API
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_engine
from app.engine.data_engine import MonitoringEngine

MIN_HISTORY_POINTS = 10
MAX_HISTORY_POINTS = 5000

router = APIRouter()


# ===== 固定路径路由（必须在 {sensor_id} 之前）=====

@router.get("/history/timerange")
async def get_time_range(engine: MonitoringEngine = Depends(get_engine)):
    """获取历史数据时间范围"""
    return engine.get_time_range()


@router.get("/history/range")
async def get_history_range(
    sensor_id: str = Query(...),
    start: float = Query(...),
    end: float = Query(...),
    max_points: int = Query(
        default=500,
        ge=MIN_HISTORY_POINTS,
        le=MAX_HISTORY_POINTS,
    ),
    engine: MonitoringEngine = Depends(get_engine),
):
    """获取指定时间范围的历史数据"""
    if not math.isfinite(start) or not math.isfinite(end):
        raise HTTPException(
            status_code=400,
            detail="start and end must be finite timestamps",
        )
    if start > end:
        raise HTTPException(status_code=400, detail="start must not be after end")
    data = engine.get_history_range(sensor_id, start, end, max_points)
    return {
        "sensor_id": sensor_id,
        "start": start,
        "end": end,
        "count": len(data),
        "data": data,
    }


@router.get("/history/snapshot")
async def get_snapshot(
    ts: float = Query(...),
    engine: MonitoringEngine = Depends(get_engine),
):
    """获取指定时间点的传感器快照"""
    if not math.isfinite(ts):
        raise HTTPException(
            status_code=400,
            detail="ts must be a finite timestamp",
        )
    return engine.get_snapshot_at(ts)


@router.get("/history/alerts")
async def get_alerts_range(
    start: float = Query(...),
    end: float = Query(...),
    engine: MonitoringEngine = Depends(get_engine),
):
    """获取指定时间范围的告警"""
    if not math.isfinite(start) or not math.isfinite(end):
        raise HTTPException(
            status_code=400,
            detail="start and end must be finite timestamps",
        )
    if start > end:
        raise HTTPException(status_code=400, detail="start must not be after end")
    data = engine.get_alerts_range(start, end)
    return {"start": start, "end": end, "count": len(data), "alerts": data}


# ===== 动态路径路由 =====

@router.get("/")
async def list_sensors(engine: MonitoringEngine = Depends(get_engine)):
    """获取所有传感器最新读数"""
    return engine.get_latest()


@router.get("/{sensor_id}")
async def get_sensor(
    sensor_id: str,
    engine: MonitoringEngine = Depends(get_engine),
):
    """获取指定传感器最新读数"""
    result = engine.get_latest(sensor_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
    return result


@router.get("/{sensor_id}/history")
async def get_sensor_history(
    sensor_id: str,
    minutes: int = Query(default=60, ge=1, le=1440),
    engine: MonitoringEngine = Depends(get_engine),
):
    """获取指定传感器最近N分钟的历史数据"""
    data = engine.get_history(sensor_id, minutes)
    return {
        "sensor_id": sensor_id,
        "minutes": minutes,
        "count": len(data),
        "data": data,
    }


@router.get("/{sensor_id}/stats")
async def get_sensor_stats(
    sensor_id: str,
    engine: MonitoringEngine = Depends(get_engine),
):
    """获取指定传感器统计信息"""
    stats = engine.get_sensor_stats(sensor_id)
    if stats is None:
        raise HTTPException(status_code=404, detail=f"No data for sensor {sensor_id}")
    return stats
