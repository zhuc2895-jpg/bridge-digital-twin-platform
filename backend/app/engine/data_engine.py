"""
数据引擎 - 改造自 smart-bridge-monitoring
负责传感器数据接入、存储、查询、统计
"""

import bisect
from collections import deque
import heapq
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SensorReading:
    """单条传感器读数"""
    sensor_id: str
    name: str
    type: str          # strain / displacement / acceleration / temperature
    value: float
    timestamp: float


@dataclass
class Alert:
    """告警记录"""
    id: str
    sensor_id: str
    sensor_name: str
    level: str         # green / yellow / orange / red
    message: str
    value: float
    threshold: float
    source: str        # rule / ml_stalwart / ml_gan_ae / dual_confirm
    timestamp: float


class MonitoringEngine:
    """
    桥梁监测数据引擎
    - O(1) 传感器查找
    - 滚动窗口历史记录
    - Top-K 峰值检测
    - 物理阈值告警
    """

    def __init__(self, window_size: int = 500, top_k: int = 10):
        self.window_size = window_size
        self.top_k = top_k

        # 传感器最新状态: dict[sensor_id] -> SensorReading
        self._latest: Dict[str, SensorReading] = {}

        # 滚动窗口历史: dict[sensor_id] -> deque(maxlen=window_size)
        self._history: Dict[str, deque] = {}

        # 全量历史（用于历史回放，最多保留10万条/传感器）
        self._full_history: Dict[str, List[SensorReading]] = {}
        self._max_full_history = 100000
        self._min_ts: Optional[float] = None
        self._max_ts: Optional[float] = None

        # Top-K 峰值堆
        self._top_spikes: List[tuple] = []  # (-value, sensor_id, timestamp)

        # 告警列表
        self._alerts: List[Alert] = []
        self._alert_counter = 0

        # 统计
        self._total_readings = 0
        self._start_time = time.time()

        # 物理阈值配置（可动态调整）
        self.thresholds = {
            "strain": {"yellow": 300, "orange": 450, "red": 600},
            "displacement": {"yellow": 30, "orange": 50, "red": 80},
            "acceleration": {"yellow": 2.0, "orange": 3.5, "red": 5.0},
            "temperature": {"yellow": 45, "orange": 55, "red": 65},
        }

    def ingest(self, sensor_data: List[dict]):
        """摄入一批传感器数据"""
        touched_full_history = set()
        unsorted_full_history = set()
        for item in sensor_data:
            reading = SensorReading(
                sensor_id=item["sensor_id"],
                name=item.get("name", ""),
                type=item.get("type", "unknown"),
                value=item["value"],
                timestamp=item.get("timestamp", time.time())
            )
            current = self._latest.get(reading.sensor_id)
            if current is None or reading.timestamp >= current.timestamp:
                self._latest[reading.sensor_id] = reading

            # 维护最近 500 条滚动窗口，并按读数时间保持有序。
            history = self._history.setdefault(reading.sensor_id, deque())
            if not history or reading.timestamp >= history[-1].timestamp:
                history.append(reading)
            else:
                timestamps = [item.timestamp for item in history]
                history.insert(bisect.bisect_right(timestamps, reading.timestamp), reading)
            if len(history) > self.window_size:
                history.popleft()

            # 维护全量历史；批量摄入结束后统一排序并按时间淘汰最旧数据。
            fh = self._full_history.setdefault(reading.sensor_id, [])
            if fh and reading.timestamp < fh[-1].timestamp:
                unsorted_full_history.add(reading.sensor_id)
            fh.append(reading)
            touched_full_history.add(reading.sensor_id)

            # 更新全局时间范围
            ts = reading.timestamp
            if self._min_ts is None or ts < self._min_ts:
                self._min_ts = ts
            if self._max_ts is None or ts > self._max_ts:
                self._max_ts = ts

            # 维护 Top-K 峰值
            heapq.heappush(self._top_spikes, (-reading.value, reading.sensor_id, reading.timestamp))
            if len(self._top_spikes) > self.top_k:
                heapq.heappop(self._top_spikes)

            self._total_readings += 1

        for sensor_id in touched_full_history:
            fh = self._full_history[sensor_id]
            if sensor_id in unsorted_full_history:
                fh.sort(key=lambda reading: reading.timestamp)
            overflow = len(fh) - self._max_full_history
            if overflow > 0:
                del fh[:overflow]

        if touched_full_history:
            histories = [history for history in self._full_history.values() if history]
            self._min_ts = min(history[0].timestamp for history in histories)
            self._max_ts = max(history[-1].timestamp for history in histories)

    def check_thresholds(self, sensor_data: List[dict]) -> List[Alert]:
        """第一层：物理阈值检测"""
        alerts = []
        for item in sensor_data:
            sensor_type = item.get("type", "unknown")
            value = item["value"]
            thresholds = self.thresholds.get(sensor_type, {})

            for level in ["red", "orange", "yellow"]:
                if level in thresholds and abs(value) >= thresholds[level]:
                    alert = Alert(
                        id=f"ALT-{self._alert_counter}",
                        sensor_id=item["sensor_id"],
                        sensor_name=item.get("name", ""),
                        level=level,
                        message=f"{item.get('name', '')} 超过{level}阈值: {value:.2f} >= {thresholds[level]}",
                        value=value,
                        threshold=thresholds[level],
                        source="rule",
                        timestamp=item.get("timestamp", time.time())
                    )
                    alerts.append(alert)
                    self._alert_counter += 1
                    break  # 只取最高级别
        return alerts

    def add_alert(self, alert: Alert):
        """添加告警，全量保留用于历史回放（最多5万条）"""
        self._alerts.append(alert)
        if len(self._alerts) > 50000:
            self._alerts = self._alerts[-50000:]

    def get_active_alerts(self) -> List[dict]:
        """获取最近20条告警"""
        return [
            {
                "id": a.id,
                "sensor_id": a.sensor_id,
                "sensor_name": a.sensor_name,
                "level": a.level,
                "message": a.message,
                "value": a.value,
                "threshold": a.threshold,
                "source": a.source,
                "timestamp": a.timestamp
            }
            for a in self._alerts[-20:]
        ]

    def get_sensor_count(self) -> int:
        return len(self._latest)

    def get_alert_count(self) -> int:
        """Return the number of retained alerts, not only the recent page."""
        return len(self._alerts)

    def get_latest(self, sensor_id: str = None) -> Optional[dict]:
        if sensor_id:
            r = self._latest.get(sensor_id)
            return self._reading_to_dict(r) if r else None
        return {sid: self._reading_to_dict(r) for sid, r in self._latest.items()}

    def get_history(self, sensor_id: str, minutes: int = 60) -> List[dict]:
        """获取指定传感器最近N分钟的历史数据"""
        if sensor_id not in self._history:
            return []
        cutoff = time.time() - minutes * 60
        return [
            self._reading_to_dict(r)
            for r in self._history[sensor_id]
            if r.timestamp >= cutoff
        ]

    def get_sensor_stats(self, sensor_id: str) -> Optional[dict]:
        """Summarize the sensor's retained rolling window."""
        readings = self._history.get(sensor_id)
        if not readings:
            return None
        values = [reading.value for reading in readings]
        latest = max(readings, key=lambda reading: reading.timestamp)
        return {
            "sensor_id": sensor_id,
            "count": len(values),
            "mean": round(sum(values) / len(values), 4),
            "max": max(values),
            "min": min(values),
            "latest": latest.value,
        }

    def get_history_range(self, sensor_id: str, start_ts: float, end_ts: float, max_points: int = 500) -> List[dict]:
        """获取指定时间范围的历史数据，支持降采样"""
        if sensor_id not in self._full_history:
            return []
        data = [
            self._reading_to_dict(r)
            for r in self._full_history[sensor_id]
            if start_ts <= r.timestamp <= end_ts
        ]
        data.sort(key=lambda x: x["timestamp"])
        # 降采样时保留首尾数据点，并在时间轴上均匀抽取。
        if len(data) > max_points:
            last_index = len(data) - 1
            data = [
                data[(index * last_index + (max_points - 1) // 2) // (max_points - 1)]
                for index in range(max_points)
            ]
        return data

    def get_time_range(self) -> dict:
        """获取全量数据的时间范围"""
        if self._min_ts is None:
            return {"start": None, "end": None, "has_data": False}
        return {"start": self._min_ts, "end": self._max_ts, "has_data": True}

    def get_alerts_range(self, start_ts: float, end_ts: float) -> List[dict]:
        """获取指定时间范围的告警"""
        return [
            {
                "id": a.id,
                "sensor_id": a.sensor_id,
                "sensor_name": a.sensor_name,
                "level": a.level,
                "message": a.message,
                "value": a.value,
                "threshold": a.threshold,
                "source": a.source,
                "timestamp": a.timestamp
            }
            for a in self._alerts
            if start_ts <= a.timestamp <= end_ts
        ]

    def get_snapshot_at(self, ts: float) -> dict:
        """获取指定时间点的传感器快照（取该时间点之前最近的一条数据）"""
        import bisect
        result = {}
        for sid, readings in self._full_history.items():
            if not readings:
                continue
            # 按时间排序后二分查找
            sorted_readings = sorted(readings, key=lambda r: r.timestamp)
            timestamps = [r.timestamp for r in sorted_readings]
            idx = bisect.bisect_right(timestamps, ts) - 1
            if idx >= 0:
                result[sid] = self._reading_to_dict(sorted_readings[idx])
        return result

    def get_top_spikes(self) -> List[dict]:
        """获取 Top-K 峰值"""
        spikes = sorted(self._top_spikes, key=lambda x: x[0])
        return [
            {"value": -s[0], "sensor_id": s[1], "timestamp": s[2]}
            for s in spikes
        ]

    def get_stats(self) -> dict:
        """获取引擎统计信息"""
        elapsed = time.time() - self._start_time
        return {
            "total_readings": self._total_readings,
            "sensor_count": len(self._latest),
            "active_alerts": len(self._alerts),
            "throughput": round(self._total_readings / elapsed, 1) if elapsed > 0 else 0,
            "uptime_seconds": round(elapsed, 1)
        }

    def _reading_to_dict(self, r: SensorReading) -> dict:
        return {
            "sensor_id": r.sensor_id,
            "name": r.name,
            "type": r.type,
            "value": r.value,
            "timestamp": r.timestamp
        }
