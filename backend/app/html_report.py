"""Render the printable HTML monitoring report from live application state."""

from __future__ import annotations

import time
from collections.abc import Mapping
from html import escape
from typing import TYPE_CHECKING, Any

from app.sensor_metrics import finite_float, is_online, is_time_valid

if TYPE_CHECKING:
    from app.dependencies import AppServices


REPORT_ALERT_LIMIT = 50

STATUS_LABELS = {
    "green": "正常",
    "yellow": "注意",
    "orange": "预警",
    "red": "报警",
}
STATUS_COLORS = {
    "green": "#389e0d",
    "yellow": "#d4b106",
    "orange": "#d46b08",
    "red": "#cf1322",
}
SENSOR_TYPE_LABELS = {
    "strain": "应变 (με)",
    "displacement": "位移 (mm)",
    "acceleration": "加速度 (m/s²)",
    "temperature": "温度 (°C)",
}
SOURCE_LABELS = {
    "rule": "物理阈值",
    "ai_stalwart": "AI-STALWART",
    "ai_gan_ae": "AI-GAN-AE",
    "ai_isolation_forest": "AI-Isolation Forest",
    "ai_dual_confirm": "AI 多模型确认",
    "ai_feature_arbitration": "AI 特征仲裁",
}


def _escape(value: object) -> str:
    return escape(str(value), quote=True)


def _format_measurement(value: object) -> str:
    number = finite_float(value)
    return "—" if number is None else f"{number:.2f}"


def _format_timestamp(value: object) -> str:
    timestamp = finite_float(value)
    if timestamp is None:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
    except (OverflowError, OSError, ValueError):
        return "—"


def _sensor_status(
    reading: Mapping[str, Any] | None,
    thresholds: Mapping[str, Any],
) -> str | None:
    if reading is None:
        return None
    sensor_type = str(reading.get("type", ""))
    value = finite_float(reading.get("value"))
    sensor_thresholds = thresholds.get(sensor_type)
    if value is None or not isinstance(sensor_thresholds, Mapping):
        return "green"
    absolute_value = abs(value)
    for level in ("red", "orange", "yellow"):
        threshold = finite_float(sensor_thresholds.get(level))
        if threshold is not None and absolute_value >= threshold:
            return level
    return "green"


def _connection_label(timestamp: Any, reference_time: float) -> tuple[str, str, bool]:
    if not is_time_valid(timestamp, reference_time):
        return "离线（时间异常）", "#cf1322", False
    if is_online(timestamp, reference_time):
        return "在线", "#389e0d", True
    return "离线", "#8c8c8c", True


def _level_counts(alerts: list[dict]) -> dict[str, int]:
    counts = {"red": 0, "orange": 0, "yellow": 0}
    for alert in alerts:
        level = alert.get("level")
        if level in counts:
            counts[level] += 1
    return counts


def _detector_summary(detector_stats: Mapping[str, Any]) -> str:
    count = int(detector_stats.get("detector_count", 0) or 0)
    if count == 0:
        return "未加载"

    detectors = detector_stats.get("detectors") or []
    degraded = sum(
        1
        for detector in detectors
        if isinstance(detector, Mapping) and detector.get("health") != "healthy"
    )
    names = "、".join(
        _escape(
            detector.get("name")
            or detector.get("id")
            or "unknown"
        )
        for detector in detectors
        if isinstance(detector, Mapping)
    )
    status = f"已加载 {count} 个"
    if degraded:
        status += f"（{degraded} 个降级）"
    else:
        status += "（全部正常）"
    return f"{status}：{names}" if names else status


def _render_sensor_rows(
    latest: Mapping[str, Mapping[str, Any]],
    time_valid_latest: Mapping[str, Mapping[str, Any]],
    thresholds: Mapping[str, Any],
    alerts: list[dict],
    reference_time: float,
) -> str:
    if not latest:
        return '<tr class="empty-state"><td colspan="8">暂无传感器数据</td></tr>'

    alert_counts: dict[str, int] = {}
    for alert in alerts:
        sensor_id = str(alert.get("sensor_id", ""))
        alert_counts[sensor_id] = alert_counts.get(sensor_id, 0) + 1

    rows: list[str] = []
    for sensor_id, reading in sorted(latest.items(), key=lambda item: str(item[0])):
        physical_source = time_valid_latest.get(sensor_id)
        status = _sensor_status(physical_source, thresholds)
        connection_label, connection_color, latest_time_valid = _connection_label(
            reading.get("timestamp"),
            reference_time,
        )
        sensor_type = str(reading.get("type", ""))
        type_label = SENSOR_TYPE_LABELS.get(sensor_type, _escape(sensor_type))
        latest_note = ""
        if not latest_time_valid:
            latest_note = '<br><span class="muted">时间异常</span>'
        if status is None or physical_source is None:
            physical_cell = '<span class="muted">未知</span>'
        else:
            physical_cell = (
                f'<span class="status" style="color:{STATUS_COLORS[status]}">'
                f"{STATUS_LABELS[status]}</span>"
                f'<br><span class="muted">'
                f"{_format_measurement(physical_source.get('value'))} · "
                f"{_format_timestamp(physical_source.get('timestamp'))}</span>"
            )
        rows.append(
            f'<tr class="sensor-row" data-sensor-id="{_escape(sensor_id)}">'
            f"<td>{_escape(sensor_id)}</td>"
            f"<td>{_escape(reading.get('name', ''))}</td>"
            f"<td>{type_label}</td>"
            f"<td>{_format_measurement(reading.get('value'))}{latest_note}</td>"
            f'<td class="status" style="color:{connection_color}">'
            f"{connection_label}</td>"
            f"<td>{physical_cell}</td>"
            f"<td>{alert_counts.get(str(sensor_id), 0)}</td>"
            f"<td>{_format_timestamp(reading.get('timestamp'))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _render_alert_rows(alerts: list[dict]) -> str:
    if not alerts:
        return (
            '<tr class="empty-state"><td colspan="7">该时段无告警记录</td></tr>'
        )

    rows: list[str] = []
    for alert in alerts:
        level = str(alert.get("level", ""))
        source = str(alert.get("source", ""))
        rows.append(
            f'<tr class="alert-row" data-alert-id="{_escape(alert.get("id", ""))}">'
            f"<td>{_format_timestamp(alert.get('timestamp'))}</td>"
            f"<td>{_escape(alert.get('sensor_name', ''))}"
            f"<br><span class=\"muted\">{_escape(alert.get('sensor_id', ''))}</span></td>"
            f'<td class="status" style="color:{STATUS_COLORS.get(level, "#333333")}">'
            f"{_escape(STATUS_LABELS.get(level, level))}</td>"
            f"<td>{_escape(alert.get('message', ''))}</td>"
            f"<td>{_format_measurement(alert.get('value'))}</td>"
            f"<td>{_format_measurement(alert.get('threshold'))}</td>"
            f"<td>{_escape(SOURCE_LABELS.get(source, source))}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_monitoring_report(
    services: AppServices,
    *,
    hours: int,
    title: str,
) -> str:
    """Build one self-contained report for the requested trailing period."""
    generated_at = time.time()

    with services.processing_lock:
        engine = services.engine
        end_ts = generated_at
        start_ts = end_ts - hours * 3600
        alerts = engine.get_alerts_range(start_ts, end_ts)
        latest = engine.get_latest() or {}
        time_valid_latest = engine.get_latest_time_valid(end_ts)
        period_reading_count = engine.get_period_reading_count(start_ts, end_ts)
        stats = engine.get_stats(reference_time=end_ts)
        detector_stats = services.detectors.get_stats()
        thresholds = {
            sensor_type: dict(levels)
            for sensor_type, levels in engine.thresholds.items()
        }
        simulator_running = bool(services.simulator.is_running)

    recent_alerts = alerts[:REPORT_ALERT_LIMIT]
    level_counts = _level_counts(alerts)
    sensor_rows = _render_sensor_rows(
        latest,
        time_valid_latest,
        thresholds,
        alerts,
        end_ts,
    )
    alert_rows = _render_alert_rows(recent_alerts)
    uptime_seconds = max(0.0, finite_float(stats.get("uptime_seconds")) or 0.0)
    throughput = max(0.0, finite_float(stats.get("throughput")) or 0.0)
    period_start = _format_timestamp(start_ts)
    period_end = _format_timestamp(end_ts)
    generated_at_label = _format_timestamp(generated_at)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="report-hours" content="{hours}">
    <meta name="report-start" content="{start_ts:.6f}">
    <meta name="report-end" content="{end_ts:.6f}">
    <title>{_escape(title)}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; padding: 32px; color: #262626; background: #ffffff;
               font-family: "Microsoft YaHei", "PingFang SC", "SimSun", sans-serif;
               line-height: 1.55; }}
        .header {{ text-align: center; border-bottom: 3px solid #1677ff;
                   padding-bottom: 18px; margin-bottom: 26px; }}
        .header h1 {{ margin: 0 0 8px; font-size: 28px; color: #0958d9; }}
        .header .meta {{ color: #595959; font-size: 13px; }}
        .print-actions {{ text-align: center; margin-bottom: 24px; }}
        .print-button {{ padding: 10px 30px; border: 0; border-radius: 6px;
                         color: #ffffff; background: #1677ff; font-size: 16px;
                         cursor: pointer; }}
        .section {{ margin-bottom: 28px; }}
        .section h2 {{ margin: 0 0 14px; padding-left: 10px; color: #0958d9;
                       border-left: 4px solid #1677ff; font-size: 18px; }}
        .summary {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));
                    gap: 14px; }}
        .summary-card {{ padding: 16px 10px; border-radius: 8px; color: #ffffff;
                         text-align: center; }}
        .summary-card .num {{ font-size: 30px; font-weight: 700; line-height: 1.2; }}
        .summary-card .label {{ margin-top: 4px; font-size: 13px; }}
        .bg-blue {{ background: #1677ff; }}
        .bg-green {{ background: #389e0d; }}
        .bg-red {{ background: #cf1322; }}
        .bg-orange {{ background: #d46b08; }}
        .bg-yellow {{ color: #262626; background: #fadb14; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ padding: 9px 10px; border: 1px solid #d9d9d9; background: #f0f5ff;
              text-align: left; font-weight: 700; }}
        td {{ padding: 8px 10px; border: 1px solid #d9d9d9; vertical-align: top; }}
        tbody tr:nth-child(even) {{ background: #fafafa; }}
        .status {{ font-weight: 700; }}
        .muted {{ color: #8c8c8c; font-size: 12px; }}
        .empty-state td {{ padding: 18px; color: #8c8c8c; text-align: center; }}
        .footer {{ margin-top: 36px; padding-top: 16px; border-top: 1px solid #d9d9d9;
                   color: #8c8c8c; text-align: center; font-size: 12px; }}
        @media print {{
            @page {{ size: A4; margin: 12mm; }}
            body {{ padding: 0; font-size: 11px; }}
            .no-print {{ display: none !important; }}
            .summary {{ grid-template-columns: repeat(6, 1fr); }}
            .section {{ break-inside: avoid; }}
            thead {{ display: table-header-group; }}
            tr {{ break-inside: avoid; }}
            .footer {{ margin-top: 20px; }}
        }}
    </style>
</head>
<body>
    <header class="header">
        <h1>{_escape(title)}</h1>
        <div class="meta">
            报告生成时间：{generated_at_label} ｜
            统计时段：{period_start} ~ {period_end} ｜
            监测时长：{hours} 小时
        </div>
    </header>

    <div class="no-print print-actions">
        <button type="button" class="print-button" onclick="window.print()">
            打印 / 导出 PDF
        </button>
    </div>

    <section class="section">
        <h2>一、监测概况</h2>
        <div class="summary">
            <div class="summary-card bg-blue">
                <div class="num" id="online-sensors">{int(stats.get("online_sensor_count", 0) or 0)}</div>
                <div class="label">在线传感器</div>
            </div>
            <div class="summary-card bg-green">
                <div class="num" id="total-readings">{int(stats.get("total_readings", 0) or 0)}</div>
                <div class="label">累计读数</div>
            </div>
            <div class="summary-card bg-blue">
                <div class="num" id="period-readings">{period_reading_count}</div>
                <div class="label">时段读数</div>
            </div>
            <div class="summary-card bg-red">
                <div class="num" id="red-alerts">{level_counts["red"]}</div>
                <div class="label">红色报警</div>
            </div>
            <div class="summary-card bg-orange">
                <div class="num" id="orange-alerts">{level_counts["orange"]}</div>
                <div class="label">橙色预警</div>
            </div>
            <div class="summary-card bg-yellow">
                <div class="num" id="yellow-alerts">{level_counts["yellow"]}</div>
                <div class="label">黄色注意</div>
            </div>
        </div>
    </section>

    <section class="section">
        <h2>二、传感器状态</h2>
        <table>
            <thead>
                <tr>
                    <th>传感器 ID</th><th>名称</th><th>类型</th><th>最新读数</th>
                    <th>连接状态</th><th>物理状态</th><th>时段告警数</th><th>最新数据时间</th>
                </tr>
            </thead>
            <tbody>{sensor_rows}</tbody>
        </table>
    </section>

    <section class="section">
        <h2>三、告警记录（最近 {REPORT_ALERT_LIMIT} 条）</h2>
        <table>
            <thead>
                <tr>
                    <th>时间</th><th>传感器</th><th>等级</th><th>告警信息</th>
                    <th>数值</th><th>阈值</th><th>检测来源</th>
                </tr>
            </thead>
            <tbody>{alert_rows}</tbody>
        </table>
    </section>

    <section class="section">
        <h2>四、系统运行状态</h2>
        <table id="system-status">
            <tbody>
                <tr><td>系统运行时长</td><td>{uptime_seconds / 3600:.1f} 小时</td></tr>
                <tr><td>数据吞吐量</td><td>{throughput:.1f} 条/秒</td></tr>
                <tr><td>已知传感器总数</td><td>{int(stats.get("sensor_count", 0) or 0)}</td></tr>
                <tr><td>仿真器状态</td><td>{'运行中' if simulator_running else '已停止'}</td></tr>
                <tr><td>保留告警总数</td><td>{int(stats.get("retained_alerts", 0) or 0)}</td></tr>
                <tr><td>检测器状态</td><td>{_detector_summary(detector_stats)}</td></tr>
                <tr><td>AI 检测总数</td><td>{int(detector_stats.get("total_detections", 0) or 0)}</td></tr>
                <tr><td>基线学习读数</td><td>{int(detector_stats.get("baseline_readings", 0) or 0)}</td></tr>
                <tr><td>状态范围</td><td>进程内</td></tr>
            </tbody>
        </table>
    </section>

    <footer class="footer">
        桥梁健康监测数字孪生平台 ｜ 本报告由系统自动生成，仅供监测参考
    </footer>
</body>
</html>"""
