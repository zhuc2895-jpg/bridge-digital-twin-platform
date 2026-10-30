"""
数据分析 REST API
"""

import time
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.dependencies import AppServices, get_services
from app.engine.simulator import UnknownSimulatorSensorError
from app.ml.registry import DetectorRegistryError
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
            services.processor.process(injected_readings)
    except UnknownSimulatorSensorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await services.broadcast_sensor_update(injected_readings)

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
        "message": f"异常已注入到传感器 {injected_sensor_id} 的下一条读数",
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
    """导出HTML格式监测报告（可直接打印为PDF）"""
    engine = services.engine
    detector = services.detectors
    end_ts = time.time()
    start_ts = end_ts - hours * 3600

    # 获取数据
    time_range = engine.get_time_range()
    if time_range["has_data"]:
        start_ts = max(start_ts, time_range["start"])
        end_ts = min(end_ts, time_range["end"])

    alerts = engine.get_alerts_range(start_ts, end_ts)
    stats = engine.get_stats()
    detector_stats = detector.get_stats()
    latest = engine.get_latest() or {}

    # 统计各等级告警
    red_count = len([a for a in alerts if a["level"] == "red"])
    orange_count = len([a for a in alerts if a["level"] == "orange"])
    yellow_count = len([a for a in alerts if a["level"] == "yellow"])

    # 传感器状态
    sensor_rows = ""
    type_names = {"strain": "应变(με)", "displacement": "位移(mm)", "acceleration": "加速度(m/s²)", "temperature": "温度(°C)"}
    level_names = {"green": "正常", "yellow": "注意", "orange": "预警", "red": "报警"}
    level_colors = {"green": "#52c41a", "yellow": "#fadb14", "orange": "#fa8c16", "red": "#ff4d4f"}

    for sid, s in sorted(latest.items()):
        # 判断该传感器告警等级
        s_alerts = [a for a in alerts if a["sensor_id"] == sid]
        max_level = "green"
        if any(a["level"] == "red" for a in s_alerts):
            max_level = "red"
        elif any(a["level"] == "orange" for a in s_alerts):
            max_level = "orange"
        elif any(a["level"] == "yellow" for a in s_alerts):
            max_level = "yellow"

        unit = type_names.get(s["type"], s["type"])
        sensor_rows += f"""
        <tr>
            <td>{sid}</td>
            <td>{s['name']}</td>
            <td>{unit}</td>
            <td>{s['value']:.2f}</td>
            <td style="color:{level_colors[max_level]};font-weight:bold">{level_names[max_level]}</td>
            <td>{len(s_alerts)}</td>
        </tr>"""

    # 告警记录
    alert_rows = ""
    for a in sorted(alerts, key=lambda x: x["timestamp"], reverse=True)[:50]:
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(a["timestamp"]))
        level_text = level_names.get(a["level"], a["level"])
        color = level_colors.get(a["level"], "#333")
        source_map = {
            "rule": "物理阈值",
            "ai_stalwart": "AI-STALWART",
            "ai_gan_ae": "AI-GAN-AE",
            "ai_isolation_forest": "AI-Isolation Forest",
            "ai_dual_confirm": "AI多模型确认",
            "ai_feature_arbitration": "AI特征仲裁",
        }
        source_text = source_map.get(a["source"], a["source"])
        alert_rows += f"""
        <tr>
            <td>{t}</td>
            <td>{a['sensor_id']}</td>
            <td style="color:{color};font-weight:bold">{level_text}</td>
            <td>{a['message']}</td>
            <td>{a['value']:.2f}</td>
            <td>{source_text}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: "Microsoft YaHei", "SimSun", sans-serif; padding: 40px; color: #333; line-height: 1.6; }}
        .header {{ text-align: center; border-bottom: 3px solid #1890ff; padding-bottom: 20px; margin-bottom: 30px; }}
        .header h1 {{ font-size: 28px; color: #1890ff; margin-bottom: 10px; }}
        .header .meta {{ color: #666; font-size: 14px; }}
        .section {{ margin-bottom: 30px; }}
        .section h2 {{ font-size: 18px; color: #1890ff; border-left: 4px solid #1890ff; padding-left: 10px; margin-bottom: 15px; }}
        .summary {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .summary-card {{ flex: 1; padding: 20px; border-radius: 8px; text-align: center; color: white; }}
        .summary-card .num {{ font-size: 32px; font-weight: bold; }}
        .summary-card .label {{ font-size: 14px; opacity: 0.9; }}
        .bg-blue {{ background: #1890ff; }}
        .bg-red {{ background: #ff4d4f; }}
        .bg-orange {{ background: #fa8c16; }}
        .bg-yellow {{ background: #fadb14; color: #333 !important; }}
        .bg-green {{ background: #52c41a; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ background: #f0f5ff; padding: 10px; text-align: left; border: 1px solid #d9d9d9; font-weight: bold; }}
        td {{ padding: 8px 10px; border: 1px solid #d9d9d9; }}
        tr:nth-child(even) {{ background: #fafafa; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; color: #999; font-size: 12px; }}
        .info-box {{ background: #e6f7ff; border: 1px solid #91d5ff; padding: 15px; border-radius: 4px; margin-bottom: 15px; }}
        @media print {{ body {{ padding: 20px; }} .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🌉 {title}</h1>
        <div class="meta">
            报告生成时间：{time.strftime("%Y-%m-%d %H:%M:%S")} ｜
            统计时段：{time.strftime("%Y-%m-%d %H:%M", time.localtime(start_ts))} ~ {time.strftime("%Y-%m-%d %H:%M", time.localtime(end_ts))} ｜
            监测时长：{hours}小时
        </div>
    </div>

    <div class="no-print" style="text-align:center;margin-bottom:20px;">
        <button onclick="window.print()" style="padding:10px 30px;font-size:16px;background:#1890ff;color:white;border:none;border-radius:4px;cursor:pointer;">📄 打印 / 导出PDF</button>
    </div>

    <div class="section">
        <h2>一、监测概况</h2>
        <div class="info-box">
            本报告由桥梁健康监测数字孪生平台自动生成。系统采用三层递进式异常检测架构：
            第一层物理阈值快速筛查，第二层STALWART+GAN-AE+IsolationForest三模型投票，第三层多窗口特征工程仲裁。
        </div>
        <div class="summary">
            <div class="summary-card bg-blue">
                <div class="num">{stats.get('sensor_count', 8)}</div>
                <div class="label">在线传感器</div>
            </div>
            <div class="summary-card bg-green">
                <div class="num">{stats.get('total_readings', 0):,}</div>
                <div class="label">累计读数</div>
            </div>
            <div class="summary-card bg-red">
                <div class="num">{red_count}</div>
                <div class="label">红色报警</div>
            </div>
            <div class="summary-card bg-orange">
                <div class="num">{orange_count}</div>
                <div class="label">橙色预警</div>
            </div>
            <div class="summary-card bg-yellow">
                <div class="num">{yellow_count}</div>
                <div class="label">黄色注意</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>二、传感器状态</h2>
        <table>
            <thead>
                <tr><th>传感器ID</th><th>名称</th><th>类型</th><th>最新读数</th><th>状态</th><th>告警次数</th></tr>
            </thead>
            <tbody>{sensor_rows}</tbody>
        </table>
    </div>

    <div class="section">
        <h2>三、告警记录（最近50条）</h2>
        <table>
            <thead>
                <tr><th>时间</th><th>传感器</th><th>等级</th><th>告警信息</th><th>数值</th><th>检测来源</th></tr>
            </thead>
            <tbody>{alert_rows if alert_rows else '<tr><td colspan="6" style="text-align:center;color:#999">该时段无告警记录</td></tr>'}</tbody>
        </table>
    </div>

    <div class="section">
        <h2>四、系统运行状态</h2>
        <table>
            <tr><td>系统运行时长</td><td>{stats.get('uptime_seconds', 0)/3600:.1f} 小时</td></tr>
            <tr><td>数据吞吐量</td><td>{stats.get('throughput', 0):.1f} 条/秒</td></tr>
            <tr><td>AI检测器状态</td><td>已加载（STALWART + GAN-AE + IsolationForest）</td></tr>
            <tr><td>AI检测总数</td><td>{detector_stats.get('total_detections', 0)}</td></tr>
            <tr><td>基线学习读数</td><td>{detector_stats.get('baseline_readings', 0)}</td></tr>
        </table>
    </div>

    <div class="footer">
        桥梁健康监测数字孪生平台 ｜ 本报告由系统自动生成，仅供参考
    </div>
</body>
</html>"""
    return html
