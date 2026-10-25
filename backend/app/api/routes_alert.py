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
    alerts = engine.get_active_alerts()
    return {"count": len(alerts), "alerts": alerts}


@router.get("/active")
async def get_active_alerts(engine: MonitoringEngine = Depends(get_engine)):
    """获取活跃告警（最近20条）"""
    return engine.get_active_alerts()


@router.get("/stats")
async def get_alert_stats(engine: MonitoringEngine = Depends(get_engine)):
    """获取告警统计"""
    all_alerts = engine.get_active_alerts()
    levels = {"red": 0, "orange": 0, "yellow": 0, "green": 0}
    sources = {
        "rule": 0,
        "ml_stalwart": 0,
        "ml_gan_ae": 0,
        "dual_confirm": 0,
        "feature_arbitration": 0,
    }

    for alert in all_alerts:
        levels[alert["level"]] = levels.get(alert["level"], 0) + 1
        sources[alert["source"]] = sources.get(alert["source"], 0) + 1

    return {"total": len(all_alerts), "by_level": levels, "by_source": sources}
