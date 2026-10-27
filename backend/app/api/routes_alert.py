"""
告警管理 REST API
"""

from fastapi import APIRouter, Depends

from app.dependencies import get_engine
from app.engine.data_engine import MonitoringEngine

router = APIRouter()


@router.get("/")
async def get_alerts(engine: MonitoringEngine = Depends(get_engine)):
    """获取最近告警列表"""
    alerts = engine.get_recent_alerts()
    return {"count": len(alerts), "alerts": alerts}


@router.get("/active")
async def get_recent_alerts(engine: MonitoringEngine = Depends(get_engine)):
    """获取最近告警（最近20条）"""
    return engine.get_recent_alerts()


@router.get("/stats")
async def get_alert_stats(engine: MonitoringEngine = Depends(get_engine)):
    """获取全部已存储告警的统计"""
    return engine.get_alert_stats()
