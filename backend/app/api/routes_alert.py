"""
告警管理 REST API
"""

from fastapi import APIRouter, Depends

from app.dependencies import get_history_read_model
from app.history_read import HistoryReadModel

router = APIRouter()


@router.get("/")
async def get_alerts(history: HistoryReadModel = Depends(get_history_read_model)):
    """获取最近告警列表"""
    alerts = history.recent_alerts()
    return {"count": len(alerts), "alerts": alerts}


@router.get("/recent")
async def get_recent_alerts(history: HistoryReadModel = Depends(get_history_read_model)):
    """获取最近告警（最近20条）"""
    return history.recent_alerts()


@router.get("/stats")
async def get_alert_stats(history: HistoryReadModel = Depends(get_history_read_model)):
    """获取全部已存储告警的统计"""
    return history.alert_stats()
