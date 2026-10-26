"""
数据引擎 - 改造自 smart-bridge-monitoring
负责传感器数据接入、存储、查询、统计
"""

import bisect
from collections import deque
import heapq
import math
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
    source: str        # rule / ai_* sources
    timestamp: float


class MonitoringEngine:
    """
    桥梁监测数据引擎
    - O(1) 传感器查找
    - 滚动窗口历史记录
    - Top-K 峰值检测
    - 物理阈值告警
    """

    MAX_ALERTS = 50_000

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

        # 告警列表与同级告警冷却
        self._alerts: List[Alert] = []
        self._alert_counter = 0
        self._alert_cooldowns: Dict[tuple[str, str], List[float]] = {}
        self._alert_cooldown_events: deque[tuple[tuple[str, str], float]] = deque()
        self._alert_cooldown_seconds = 10.0

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
        ingested_sensor_ids = set()
        sensors_needing_sort = set()
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

            # 维护最近 500 条滚动窗口；超过容量后按到达顺序淘汰。
            history = self._history.setdefault(
                reading.sensor_id, deque(maxlen=self.window_size)
            )
            history.append(reading)

            # 维护全量历史；批量摄入结束后统一排序并按时间淘汰最旧数据。
            fh = self._full_history.setdefault(reading.sensor_id, [])
            if fh and reading.timestamp < fh[-1].timestamp:
                sensors_needing_sort.add(reading.sensor_id)
            fh.append(reading)
            ingested_sensor_ids.add(reading.sensor_id)

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

        for sensor_id in ingested_sensor_ids:
            fh = self._full_history[sensor_id]
            if sensor_id in sensors_needing_sort:
                fh.sort(key=lambda reading: reading.timestamp)
            overflow = len(fh) - self._max_full_history
            if overflow > 0:
                del fh[:overflow]

        if ingested_sensor_ids:
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
            level = next(
                (
                    candidate
                    for candidate in ("red", "orange", "yellow")
                    if candidate in thresholds
                    and abs(value) >= thresholds[candidate]
                ),
                None,
            )
            if level is None:
                continue

            timestamp = item.get("timestamp", time.time())
            cooldown_key = (item["sensor_id"], level)
            # Retain alert times so backfilled readings are checked against
            # every nearby alert, not only the most recent arrival.
            alert_times = self._alert_cooldowns.setdefault(cooldown_key, [])
            first_possible_match = bisect.bisect_right(
                alert_times,
                timestamp - self._alert_cooldown_seconds,
            )
            if (
                first_possible_match < len(alert_times)
                and alert_times[first_possible_match]
                < timestamp + self._alert_cooldown_seconds
            ):
                continue

            threshold = thresholds[level]
            alert = Alert(
                id=f"ALT-{self._alert_counter}",
                sensor_id=item["sensor_id"],
                sensor_name=item.get("name", ""),
                level=level,
                message=(
                    f"{item.get('name', '')} 超过{level}阈值: "
                    f"{abs(value):.2f} >= {threshold}"
                ),
                value=value,
                threshold=threshold,
                source="rule",
                timestamp=timestamp,
            )
            alerts.append(alert)
            self._remember_alert_time(cooldown_key, timestamp)
            self._alert_counter += 1
        return alerts

    def _remember_alert_time(
        self,
        cooldown_key: tuple[str, str],
        timestamp: float,
    ) -> None:
        alert_times = self._alert_cooldowns[cooldown_key]
        bisect.insort(alert_times, timestamp)
        self._alert_cooldown_events.append((cooldown_key, timestamp))
        while len(self._alert_cooldown_events) > self.MAX_ALERTS:
            old_key, old_timestamp = self._alert_cooldown_events.popleft()
            old_times = self._alert_cooldowns.get(old_key)
            if old_times is None:
                continue
            old_index = bisect.bisect_left(old_times, old_timestamp)
            if old_index < len(old_times) and old_times[old_index] == old_timestamp:
                old_times.pop(old_index)
            if not old_times:
                del self._alert_cooldowns[old_key]

    def update_thresholds(
        self,
        updates: Dict[str, Dict[str, float]],
    ) -> Dict[str, Dict[str, float]]:
        """Validate and atomically replace configurable threshold values."""
        candidate = {
            sensor_type: dict(levels)
            for sensor_type, levels in self.thresholds.items()
        }
        for sensor_type, levels in updates.items():
            if sensor_type not in candidate:
                raise ValueError(f"Unknown sensor type: {sensor_type}")
            for level, value in levels.items():
                if value is None:
                    continue
                if level not in candidate[sensor_type]:
                    raise ValueError(f"Unknown threshold level: {sensor_type}.{level}")
                candidate[sensor_type][level] = value

        for sensor_type, levels in candidate.items():
            ordered_values = [levels[level] for level in ("yellow", "orange", "red")]
            if any(not math.isfinite(value) or value <= 0 for value in ordered_values):
                raise ValueError(
                    f"{sensor_type} thresholds must be finite positive numbers"
                )
            if ordered_values != sorted(ordered_values):
                raise ValueError(
                    f"{sensor_type} thresholds must be ordered yellow <= orange <= red"
                )

        self.thresholds = candidate
        return candidate

    def add_alert(self, alert: Alert):
        """添加告警，全量保留用于历史回放（最多5万条）"""
        self._alerts.append(alert)
        if len(self._alerts) > self.MAX_ALERTS:
            self._alerts = self._alerts[-self.MAX_ALERTS:]

    def get_active_alerts(self) -> List[dict]:
        """获取最近20条告警"""
        return [
            self._alert_to_dict(alert)
            for alert in sorted(
                self._alerts,
                key=lambda alert: alert.timestamp,
                reverse=True,
            )[:20]
        ]

    def get_alert_stats(self) -> dict:
        """Summarize every retained alert, not only the recent page."""
        levels = {"red": 0, "orange": 0, "yellow": 0, "green": 0}
        sources = {
            "rule": 0,
            "ml_stalwart": 0,
            "ml_gan_ae": 0,
            "dual_confirm": 0,
            "feature_arbitration": 0,
        }
        for alert in self._alerts:
            levels[alert.level] = levels.get(alert.level, 0) + 1
            sources[alert.source] = sources.get(alert.source, 0) + 1
        return {
            "total": len(self._alerts),
            "by_level": levels,
            "by_source": sources,
        }

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
            for r in sorted(
                (r for r in self._history[sensor_id] if r.timestamp >= cutoff),
                key=lambda r: r.timestamp,
            )
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
        if len(data) > max_points:
            data = self._select_uniform_time_points(data, max_points)
        return data

    @staticmethod
    def _select_uniform_time_points(data: List[dict], max_points: int) -> List[dict]:
        """Select real source points nearest to uniformly spaced timestamps."""
        timestamps = [item["timestamp"] for item in data]
        first_timestamp = timestamps[0]
        last_timestamp = timestamps[-1]
        selected: List[dict] = []
        cursor = 0
        for index in range(max_points):
            target = first_timestamp + (
                (last_timestamp - first_timestamp) * index / (max_points - 1)
            )
            last_selectable = len(data) - (max_points - index)
            insertion = bisect.bisect_left(
                timestamps,
                target,
                cursor,
                last_selectable + 1,
            )
            if insertion <= cursor:
                chosen = cursor
            elif insertion > last_selectable:
                chosen = last_selectable
            else:
                left = insertion - 1
                if left < cursor:
                    chosen = insertion
                elif target - timestamps[left] <= timestamps[insertion] - target:
                    chosen = left
                else:
                    chosen = insertion
            selected.append(data[chosen])
            cursor = chosen + 1
        return selected

    def get_time_range(self) -> dict:
        """获取全量数据的时间范围"""
        if self._min_ts is None:
            return {"start": None, "end": None, "has_data": False}
        return {"start": self._min_ts, "end": self._max_ts, "has_data": True}

    def get_alerts_range(self, start_ts: float, end_ts: float) -> List[dict]:
        """获取指定时间范围的告警"""
        return [
            self._alert_to_dict(alert)
            for alert in sorted(
                (
                    alert
                    for alert in self._alerts
                    if start_ts <= alert.timestamp <= end_ts
                ),
                key=lambda alert: alert.timestamp,
                reverse=True,
            )
        ]

    def get_snapshot_at(self, ts: float) -> dict:
        """获取指定时间点的传感器快照（取该时间点之前最近的一条数据）"""
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

    @staticmethod
    def _alert_to_dict(alert: Alert) -> dict:
        return {
            "id": alert.id,
            "sensor_id": alert.sensor_id,
            "sensor_name": alert.sensor_name,
            "level": alert.level,
            "message": alert.message,
            "value": alert.value,
            "threshold": alert.threshold,
            "source": alert.source,
            "timestamp": alert.timestamp,
        }

    def _reading_to_dict(self, r: SensorReading) -> dict:
        return {
            "sensor_id": r.sensor_id,
            "name": r.name,
            "type": r.type,
            "value": r.value,
            "timestamp": r.timestamp
        }
