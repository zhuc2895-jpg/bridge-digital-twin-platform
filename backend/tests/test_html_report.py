from __future__ import annotations

import re
import time

import pytest
from app.sensor_batch import LiveEligibility, SensorBatch

from tests.factories import reading


def _card_value(html: str, card_id: str) -> str:
    match = re.search(
        rf'<div class="num" id="{re.escape(card_id)}">([^<]*)</div>',
        html,
    )
    assert match is not None, f"missing summary card {card_id}"
    return match.group(1).strip()


def _meta_value(html: str, name: str) -> str:
    match = re.search(
        rf'<meta name="{re.escape(name)}" content="([^"]*)">',
        html,
    )
    assert match is not None, f"missing meta value {name}"
    return match.group(1)


def _row_count(html: str, row_class: str) -> int:
    return len(re.findall(rf'<tr class="{re.escape(row_class)}"', html))


def _sensor_row(html: str, sensor_id: str) -> str:
    match = re.search(
        rf'<tr class="sensor-row" data-sensor-id="{re.escape(sensor_id)}">'
        r"(.*?)</tr>",
        html,
        re.DOTALL,
    )
    assert match is not None, f"missing sensor row {sensor_id}"
    return match.group(0)


def _system_status_value(html: str, label: str) -> str:
    match = re.search(
        rf"<tr><td>{re.escape(label)}</td><td>(.*?)</td></tr>",
        html,
        re.DOTALL,
    )
    assert match is not None, f"missing system status row {label}"
    return match.group(1).strip()


@pytest.mark.parametrize(
    ("params", "expected_hours"),
    [
        ({}, "24"),
        ({"hours": "1"}, "1"),
        ({"hours": "168"}, "168"),
    ],
)
def test_report_uses_default_and_boundary_periods(client, params, expected_hours):
    response = client.get("/api/analysis/report", params=params)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert _meta_value(response.text, "report-hours") == expected_hours
    start = float(_meta_value(response.text, "report-start"))
    end = float(_meta_value(response.text, "report-end"))
    assert end - start == pytest.approx(int(expected_hours) * 3600)


@pytest.mark.parametrize("hours", ["0", "169", "abc", "1.5", "-1"])
def test_report_rejects_invalid_periods_with_400(client, hours):
    response = client.get("/api/analysis/report", params={"hours": hours})

    assert response.status_code == 400
    assert "detail" in response.json()


def test_report_has_explicit_empty_states_without_any_data(client):
    response = client.get("/api/analysis/report", params={"hours": 24})

    assert response.status_code == 200
    assert _card_value(response.text, "online-sensors") == "0"
    assert _card_value(response.text, "total-readings") == "0"
    assert _card_value(response.text, "period-readings") == "0"
    assert _card_value(response.text, "red-alerts") == "0"
    assert _card_value(response.text, "orange-alerts") == "0"
    assert _card_value(response.text, "yellow-alerts") == "0"
    assert _row_count(response.text, "sensor-row") == 0
    assert _row_count(response.text, "alert-row") == 0
    assert "暂无传感器数据" in response.text
    assert "该时段无告警记录" in response.text


def test_report_uses_period_alerts_and_current_sensor_state(client, app):
    now = time.time()
    records = [
        reading(
            sensor_id="S-NORMAL",
            name="Normal sensor",
            value=100.0,
            timestamp=now - 30,
        ),
        reading(
            sensor_id="S-YELLOW",
            name="Yellow sensor",
            value=300.0,
            timestamp=now - 20,
        ),
        reading(
            sensor_id="S-ORANGE",
            name="Orange sensor",
            value=450.0,
            timestamp=now - 10,
        ),
        reading(
            sensor_id="S-RED",
            name="Red sensor",
            value=600.0,
            timestamp=now - 5,
        ),
    ]
    upload = client.post("/api/data/upload/json?push_live=false", json=records)
    assert upload.status_code == 200

    app.state.services.engine.submit_alert(
        sensor_id="S-OLD",
        sensor_name="Old sensor",
        level="red",
        message="outside the requested period",
        value=600.0,
        threshold=600.0,
        source="rule",
        timestamp=now - 7200,
    )

    response = client.get("/api/analysis/report", params={"hours": 1})

    assert response.status_code == 200
    assert _card_value(response.text, "online-sensors") == "4"
    assert _card_value(response.text, "total-readings") == "4"
    assert _card_value(response.text, "period-readings") == "4"
    assert _card_value(response.text, "red-alerts") == "1"
    assert _card_value(response.text, "orange-alerts") == "1"
    assert _card_value(response.text, "yellow-alerts") == "1"
    assert _row_count(response.text, "sensor-row") == 4
    assert _row_count(response.text, "alert-row") == 3
    assert "outside the requested period" not in response.text

    assert response.text.index("Red sensor 超过red阈值") < response.text.index(
        "Orange sensor 超过orange阈值"
    )
    assert response.text.index("Orange sensor 超过orange阈值") < response.text.index(
        "Yellow sensor 超过yellow阈值"
    )
    assert ">600.00<" in response.text
    assert "报警" in response.text
    assert "预警" in response.text
    assert "注意" in response.text
    assert "正常" in response.text


def test_report_separates_connection_and_physical_state(client, app):
    now = time.time()
    engine = app.state.services.engine
    records = [
        reading(
            sensor_id="S-ONLINE",
            name="Online sensor",
            value=100.0,
            timestamp=now - 10,
        ),
        reading(
            sensor_id="S-OFFLINE",
            name="Stale sensor",
            value=300.0,
            timestamp=now - 120,
        ),
        reading(
            sensor_id="S-FUTURE-ONLINE",
            name="Future within tolerance",
            value=450.0,
            timestamp=now + 30,
        ),
        reading(
            sensor_id="S-TIME-INVALID-VALID-HISTORY",
            name="Invalid future with history",
            value=100.0,
            timestamp=now - 30,
        ),
        reading(
            sensor_id="S-TIME-INVALID-VALID-HISTORY",
            name="Invalid future with history",
            value=600.0,
            timestamp=now + 61,
        ),
        reading(
            sensor_id="S-TIME-INVALID-NO-HISTORY",
            name="Invalid future without history",
            value=600.0,
            timestamp=now + 61,
        ),
    ]
    for record in records:
        engine.ingest(
            SensorBatch(records=[record], live_eligibility=LiveEligibility.BACKFILL)
        )

    response = client.get("/api/analysis/report", params={"hours": 1})
    health = client.get("/api/health")

    assert response.status_code == 200
    assert health.status_code == 200
    assert _card_value(response.text, "online-sensors") == "2"
    assert _card_value(response.text, "total-readings") == "6"
    assert _card_value(response.text, "period-readings") == "3"
    assert health.json()["sensor_count"] == 5
    assert health.json()["online_sensor_count"] == 2
    assert _row_count(response.text, "sensor-row") == 5

    rows = {
        sensor_id: _sensor_row(response.text, sensor_id)
        for sensor_id in (
            "S-ONLINE",
            "S-OFFLINE",
            "S-FUTURE-ONLINE",
            "S-TIME-INVALID-VALID-HISTORY",
            "S-TIME-INVALID-NO-HISTORY",
        )
    }
    assert "在线" in rows["S-ONLINE"]
    assert "正常" in rows["S-ONLINE"]
    assert "离线" in rows["S-OFFLINE"]
    assert "注意" in rows["S-OFFLINE"]
    assert "在线" in rows["S-FUTURE-ONLINE"]
    assert "预警" in rows["S-FUTURE-ONLINE"]
    assert "离线（时间异常）" in rows["S-TIME-INVALID-VALID-HISTORY"]
    assert "正常" in rows["S-TIME-INVALID-VALID-HISTORY"]
    assert "报警" not in rows["S-TIME-INVALID-VALID-HISTORY"]
    assert "离线（时间异常）" in rows["S-TIME-INVALID-NO-HISTORY"]
    assert "未知" in rows["S-TIME-INVALID-NO-HISTORY"]


def test_report_limits_alert_rows_to_newest_fifty_but_keeps_counts(client, app):
    now = time.time()
    engine = app.state.services.engine
    for index in range(55):
        engine.submit_alert(
            sensor_id=f"TRUNC-{index:02d}",
            sensor_name=f"Truncated sensor {index:02d}",
            level="yellow",
            message=f"truncated-alert-{index:02d}",
            value=300.0,
            threshold=300.0,
            source="rule",
            timestamp=now - 120 + index,
        )

    response = client.get("/api/analysis/report", params={"hours": 1})

    assert response.status_code == 200
    assert _card_value(response.text, "yellow-alerts") == "55"
    assert _row_count(response.text, "alert-row") == 50
    for index in range(5, 55):
        assert f"truncated-alert-{index:02d}" in response.text
    for index in range(5):
        assert f"truncated-alert-{index:02d}" not in response.text


def test_report_system_status_matches_live_services(client, app):
    now = time.time()
    services = app.state.services
    upload = client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(
                sensor_id="S-SYSTEM",
                name="System status sensor",
                value=600.0,
                timestamp=now - 1,
            )
        ],
    )
    assert upload.status_code == 200
    services.simulator.is_running = True
    engine_stats = services.engine.get_stats()
    detector_stats = services.detectors.get_stats()

    response = client.get("/api/analysis/report", params={"hours": 1})

    assert response.status_code == 200
    assert _system_status_value(response.text, "仿真器状态") == "运行中"
    assert _system_status_value(response.text, "保留告警总数") == str(
        engine_stats["retained_alerts"]
    )
    detector_status = _system_status_value(response.text, "检测器状态")
    assert f"已加载 {detector_stats['detector_count']} 个" in detector_status
    assert _system_status_value(response.text, "AI 检测总数") == str(
        detector_stats["total_detections"]
    )
    assert _system_status_value(response.text, "基线学习读数") == str(
        detector_stats["baseline_readings"]
    )
    uptime = _system_status_value(response.text, "系统运行时长")
    throughput = _system_status_value(response.text, "数据吞吐量")
    assert uptime.endswith(" 小时")
    assert float(uptime.removesuffix(" 小时")) >= 0
    assert throughput.endswith(" 条/秒")
    assert float(throughput.removesuffix(" 条/秒")) >= 0


def test_report_escapes_dynamic_content_and_has_print_styles(client):
    now = time.time()
    malicious_name = '<img src=x onerror="alert(1)">'
    upload = client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(
                sensor_id="S-ESCAPE",
                name=malicious_name,
                value=600.0,
                timestamp=now - 1,
            )
        ],
    )
    assert upload.status_code == 200

    response = client.get(
        "/api/analysis/report",
        params={"hours": 1, "title": "<script>alert('title')</script>"},
    )

    assert response.status_code == 200
    assert malicious_name not in response.text
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in response.text
    assert "<script>alert('title')</script>" not in response.text
    assert "&lt;script&gt;alert(&#x27;title&#x27;)&lt;/script&gt;" in response.text
    assert 'class="no-print print-actions"' in response.text
    assert "window.print()" in response.text
    assert "@media print" in response.text
    assert ".no-print { display: none !important; }" in response.text
