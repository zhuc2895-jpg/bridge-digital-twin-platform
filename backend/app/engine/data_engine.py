"""
数据引擎 - 改造自 smart-bridge-monitoring
负责传感器数据接入、存储、查询、统计
"""

import bisect
import heapq
import math
import time
import uuid
from array import array
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from app.alert_contracts import (
    ALERT_LEVELS as CANONICAL_ALERT_LEVELS,
)
from app.alert_contracts import (
    ALERT_SOURCES as CANONICAL_ALERT_SOURCES,
)
from app.sensor_batch import SensorBatch
from app.sensor_ids import SensorIdentifier
from app.sensor_metrics import (
    ONLINE_SENSOR_FRESHNESS_SECONDS,
    is_online,
)
from app.sensor_types import SensorType

# Keep enough timestamps to answer the maximum supported 168-hour report.
_READING_TIMESTAMP_RETENTION_SECONDS = (168 + 1) * 3600.0


@dataclass
class SensorReading:
    """单条传感器读数"""
    sensor_id: SensorIdentifier
    name: str
    type: SensorType  # strain / displacement / acceleration / temperature
    value: float
    timestamp: float
    live_eligible: bool = True


@dataclass
class Alert:
    """告警记录"""
    id: uuid.UUID
    sensor_id: str
    sensor_name: str
    level: str         # yellow / orange / red
    message: str
    value: float
    threshold: float
    source: str        # rule / ai_* sources
    timestamp: float | None
    detection_sequence: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    live_eligible: bool = True


class MonitoringEngine:
    """
    桥梁监测数据引擎
    - O(1) 传感器查找
    - 滚动窗口历史记录
    - Top-K 峰值检测
    - 物理阈值告警
    """

    MAX_ALERTS = 50_000
    ALERT_LEVELS = CANONICAL_ALERT_LEVELS
    ALERT_SOURCES = CANONICAL_ALERT_SOURCES

    def __init__(self, window_size: int = 500, top_k: int = 10):
        self.window_size = window_size
        self.top_k = top_k

        # 传感器最新状态: dict[sensor_id] -> SensorReading
        self._latest: Dict[str, SensorReading] = {}
        self._live_latest: Dict[str, SensorReading] = {}
        self._pending_external_versions: Dict[str, int] = {}
        self._external_version = 0

        # 滚动窗口历史: dict[sensor_id] -> deque(maxlen=window_size)
        self._history: Dict[str, deque] = {}

        # 全量历史（用于历史回放，最多保留10万条/传感器）
        self._full_history: Dict[str, List[SensorReading]] = {}
        self._max_full_history = 100000
        self._reading_timestamps: Dict[str, array] = {}
        self._reading_retention_anchor: Optional[float] = None
        self._latest_time_valid: Dict[str, SensorReading] = {}
        self._future_readings: Dict[str, List[SensorReading]] = {}
        self._min_ts: Optional[float] = None
        self._max_ts: Optional[float] = None

        # Top-K 峰值堆
        self._top_spikes: List[tuple] = []  # (-value, sensor_id, timestamp)

        # 告警列表与同级告警冷却
        self._alerts: List[Alert] = []
        self._detection_sequence = 0
        self._alert_cooldowns: Dict[tuple[str, str], List[float]] = {}
        self._alert_cooldown_events: deque[tuple[tuple[str, str], float]] = deque()
        self._alert_cooldown_seconds = 10.0

        # 统计
        self._total_readings = 0
        self._start_time = time.time()

        # 物理阈值配置（可动态调整）
        self.thresholds: Dict[str, Dict[str, float]] = {
            "strain": {"yellow": 300, "orange": 450, "red": 600},
            "displacement": {"yellow": 30, "orange": 50, "red": 80},
            "acceleration": {"yellow": 2.0, "orange": 3.5, "red": 5.0},
            "temperature": {"yellow": 45, "orange": 55, "red": 65},
        }

    def ingest(self, batch: SensorBatch):
        """摄入一批传感器数据，并应用该批次的实时可见性策略。"""
        ingested_sensor_ids = set()
        sensors_needing_sort = set()
        timestamps_needing_sort = set()
        ingestion_now = time.time()
        for item in batch.records:
            reading = SensorReading(
                sensor_id=item["sensor_id"],
                name=item.get("name", ""),
                type=item.get("type", "unknown"),
                value=item["value"],
                timestamp=item.get("timestamp", time.time()),
                live_eligible=batch.live_eligibility.is_live,
            )
            current = self._latest.get(reading.sensor_id)
            if current is None or reading.timestamp >= current.timestamp:
                self._latest[reading.sensor_id] = reading
            if batch.live_eligibility.is_live:
                current_live = self._live_latest.get(reading.sensor_id)
                if (
                    current_live is None
                    or reading.timestamp >= current_live.timestamp
                ):
                    self._live_latest[reading.sensor_id] = reading
                if batch.live_eligibility.is_external:
                    self._external_version += 1
                    self._pending_external_versions[reading.sensor_id] = (
                        self._external_version
                    )

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

            # 保留独立的读数时间索引，使时段计数不受全量历史淘汰影响。
            timestamps = self._reading_timestamps.setdefault(
                reading.sensor_id,
                array("d"),
            )
            if timestamps and reading.timestamp < timestamps[-1]:
                timestamps_needing_sort.add(reading.sensor_id)
            timestamps.append(reading.timestamp)
            if (
                reading.timestamp
                <= ingestion_now + ONLINE_SENSOR_FRESHNESS_SECONDS
                and (
                    self._reading_retention_anchor is None
                    or reading.timestamp > self._reading_retention_anchor
                )
            ):
                self._reading_retention_anchor = reading.timestamp
            if reading.timestamp <= (
                ingestion_now + ONLINE_SENSOR_FRESHNESS_SECONDS
            ):
                current_valid = self._latest_time_valid.get(reading.sensor_id)
                if (
                    current_valid is None
                    or reading.timestamp >= current_valid.timestamp
                ):
                    self._latest_time_valid[reading.sensor_id] = reading
            else:
                bisect.insort(
                    self._future_readings.setdefault(reading.sensor_id, []),
                    reading,
                    key=lambda candidate: candidate.timestamp,
                )

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
            if sensor_id in timestamps_needing_sort:
                self._reading_timestamps[sensor_id] = array(
                    "d",
                    sorted(self._reading_timestamps[sensor_id]),
                )
            self._trim_reading_timestamps(sensor_id)

        if ingested_sensor_ids:
            histories = [history for history in self._full_history.values() if history]
            self._min_ts = min(history[0].timestamp for history in histories)
            self._max_ts = max(history[-1].timestamp for history in histories)

    def check_thresholds(self, batch: SensorBatch) -> List[Alert]:
        """Evaluate physical thresholds and submit every matched alert."""
        alerts = []
        for item in batch.records:
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

            threshold = thresholds[level]
            alert = self.submit_alert(
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
                timestamp=item.get("timestamp", time.time()),
                live_eligible=batch.live_eligibility.is_live,
            )
            if alert is not None:
                alerts.append(alert)
        return alerts

    def is_normal_reading(self, item: Mapping[str, Any]) -> bool:
        """Return whether a reading is below its type's yellow threshold."""
        thresholds = self.thresholds.get(item.get("type", "unknown"))
        if not thresholds:
            return True
        return abs(float(item["value"])) < thresholds["yellow"]

    def submit_alert(
        self,
        *,
        sensor_id: str,
        sensor_name: str,
        level: str,
        message: str,
        value: float,
        threshold: float,
        source: str,
        timestamp: float | None,
        details: Optional[Mapping[str, Any]] = None,
        live_eligible: bool = True,
    ) -> Optional[Alert]:
        """Create one alert through the shared lifecycle policy."""
        if level not in self.ALERT_LEVELS:
            raise ValueError(f"Unknown alert level: {level}")
        if source not in self.ALERT_SOURCES:
            raise ValueError(f"Unknown alert source: {source}")
        try:
            sensor_id = str(SensorIdentifier(sensor_id))
        except ValueError as exc:
            raise ValueError(f"Invalid alert sensor_id: {exc}") from exc
        normalized_timestamp = self._normalize_alert_timestamp(timestamp)
        if (
            normalized_timestamp is not None
            and self._is_alert_in_cooldown(
                sensor_id,
                level,
                normalized_timestamp,
            )
        ):
            return None

        alert = Alert(
            id=uuid.uuid4(),
            sensor_id=sensor_id,
            sensor_name=sensor_name,
            level=level,
            message=message,
            value=value,
            threshold=threshold,
            source=source,
            timestamp=normalized_timestamp,
            details=dict(details or {}),
            live_eligible=live_eligible,
        )
        if normalized_timestamp is not None:
            self._remember_alert_time((sensor_id, level), normalized_timestamp)
        self._retain_alert(alert)
        return alert

    def _is_alert_in_cooldown(
        self,
        sensor_id: str,
        level: str,
        timestamp: float,
    ) -> bool:
        alert_times = self._alert_cooldowns.get((sensor_id, level))
        if not alert_times:
            return False
        first_possible_match = bisect.bisect_right(
            alert_times,
            timestamp - self._alert_cooldown_seconds,
        )
        return (
            first_possible_match < len(alert_times)
            and alert_times[first_possible_match]
            < timestamp + self._alert_cooldown_seconds
        )

    def _remember_alert_time(
        self,
        cooldown_key: tuple[str, str],
        timestamp: float,
    ) -> None:
        alert_times = self._alert_cooldowns.setdefault(cooldown_key, [])
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
        updates: Dict[str, Dict[str, Optional[float]]],
    ) -> Dict[str, Dict[str, float]]:
        """Validate and atomically replace configurable threshold values."""
        candidate: Dict[str, Dict[str, float]] = {
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

        for sensor_type, candidate_levels in candidate.items():
            ordered_values = [
                candidate_levels[level] for level in ("yellow", "orange", "red")
            ]
            if any(
                not math.isfinite(threshold_value) or threshold_value <= 0
                for threshold_value in ordered_values
            ):
                raise ValueError(
                    f"{sensor_type} thresholds must be finite positive numbers"
                )
            if any(
                lower >= higher
                for lower, higher in zip(ordered_values, ordered_values[1:])
            ):
                raise ValueError(
                    f"{sensor_type} thresholds must be strictly ordered "
                    "yellow < orange < red"
                )

        changed_types = {
            sensor_type
            for sensor_type, levels in candidate.items()
            if levels != self.thresholds[sensor_type]
        }
        self.thresholds = candidate
        self._clear_cooldowns_for_sensor_types(changed_types)
        return candidate

    def _clear_cooldowns_for_sensor_types(self, sensor_types: set[str]) -> None:
        if not sensor_types:
            return
        affected_keys = {
            key
            for key in self._alert_cooldowns
            if key[0] in self._latest
            and self._latest[key[0]].type in sensor_types
        }
        for key in affected_keys:
            del self._alert_cooldowns[key]
        if affected_keys:
            self._alert_cooldown_events = deque(
                event
                for event in self._alert_cooldown_events
                if event[0] not in affected_keys
            )

    def _retain_alert(self, alert: Alert):
        """Retain an alert created by submit_alert."""
        if alert.detection_sequence <= 0:
            self._detection_sequence += 1
            alert.detection_sequence = self._detection_sequence
        else:
            self._detection_sequence = max(
                self._detection_sequence,
                alert.detection_sequence,
            )
        self._alerts.append(alert)
        if len(self._alerts) > self.MAX_ALERTS:
            self._alerts.sort(key=self._alert_sort_key)
            del self._alerts[:-self.MAX_ALERTS]

    @staticmethod
    def _normalize_alert_timestamp(timestamp: float | None) -> float | None:
        """Return a finite event time or None when an alert timestamp is malformed."""
        if timestamp is None or isinstance(timestamp, bool):
            return None
        try:
            normalized = float(timestamp)
        except (OverflowError, TypeError, ValueError):
            return None
        return normalized if math.isfinite(normalized) else None

    @staticmethod
    def _alert_sort_key(alert: Alert) -> tuple[float, int]:
        """Sort malformed event times last without breaking valid alert ordering."""
        timestamp = MonitoringEngine._normalize_alert_timestamp(alert.timestamp)
        return (
            timestamp if timestamp is not None else float("-inf"),
            alert.detection_sequence,
        )

    def _recent_alert_dicts(
        self,
        *,
        live_only: bool = False,
    ) -> List[dict]:
        alerts = (
            (alert for alert in self._alerts if alert.live_eligible)
            if live_only
            else self._alerts
        )
        return [
            self._alert_to_dict(alert)
            for alert in sorted(
                alerts,
                key=self._alert_sort_key,
                reverse=True,
            )[:20]
        ]

    def get_recent_alerts(self) -> List[dict]:
        """获取最近20条告警"""
        return self._recent_alert_dicts()

    def get_recent_live_alerts(self) -> List[dict]:
        """Return the newest retained alerts created by Live Eligible data."""
        return self._recent_alert_dicts(live_only=True)

    def get_live_snapshot(self, limit: int = 32) -> List[dict]:
        """Return the newest Live Eligible reading for each sensor."""
        readings = sorted(
            self._live_latest.values(),
            key=lambda reading: (reading.timestamp, str(reading.sensor_id)),
            reverse=True,
        )
        return [self._reading_to_dict(reading) for reading in readings[:limit]]

    def get_pending_external_versions(self) -> Dict[str, int]:
        return dict(self._pending_external_versions)

    def consume_pending_external(self, versions: Mapping[str, int]) -> None:
        for sensor_id, version in versions.items():
            if self._pending_external_versions.get(sensor_id) == version:
                del self._pending_external_versions[sensor_id]

    def get_alert_stats(self) -> dict:
        """Summarize every retained alert, not only the recent page."""
        levels = {level: 0 for level in self.ALERT_LEVELS}
        sources = {source: 0 for source in self.ALERT_SOURCES}
        for alert in self._alerts:
            if alert.level in levels:
                levels[alert.level] += 1
            if alert.source in sources:
                sources[alert.source] += 1
        return {
            "total": len(self._alerts),
            "by_level": levels,
            "by_source": sources,
        }

    def get_sensor_count(self) -> int:
        """Return the number of Known Sensors in this process."""
        return len(self._latest)

    def get_online_sensor_count(self, reference_time: Optional[float] = None) -> int:
        """Count Known Sensors whose latest reading is currently online."""
        reference = time.time() if reference_time is None else reference_time
        return sum(
            is_online(reading.timestamp, reference)
            for reading in self._latest.values()
        )

    def get_latest_time_valid(
        self,
        reference_time: float,
    ) -> Dict[str, dict]:
        """Return each sensor's latest reading that is not too far in the future."""
        cutoff = reference_time + ONLINE_SENSOR_FRESHNESS_SECONDS
        candidates: Dict[str, SensorReading] = {}

        def consider(reading: SensorReading) -> None:
            if reading.timestamp > cutoff:
                return
            current = candidates.get(reading.sensor_id)
            if current is None or reading.timestamp >= current.timestamp:
                candidates[reading.sensor_id] = reading

        for reading in self._latest_time_valid.values():
            consider(reading)
        for readings in self._full_history.values():
            if not readings:
                continue
            index = bisect.bisect_right(
                readings,
                cutoff,
                key=lambda reading: reading.timestamp,
            ) - 1
            if index >= 0:
                consider(readings[index])
        for future_readings in self._future_readings.values():
            index = bisect.bisect_right(
                future_readings,
                cutoff,
                key=lambda reading: reading.timestamp,
            ) - 1
            if index < 0:
                continue
            consider(future_readings[index])
        return {
            sensor_id: self._reading_to_dict(reading)
            for sensor_id, reading in candidates.items()
        }

    def get_period_reading_count(self, start_ts: float, end_ts: float) -> int:
        """Count readings by timestamp in an inclusive period across all paths."""
        if start_ts > end_ts:
            raise ValueError("start_ts must not be after end_ts")
        count = 0
        for timestamps in self._reading_timestamps.values():
            count += bisect.bisect_right(timestamps, end_ts) - bisect.bisect_left(
                timestamps,
                start_ts,
            )
        return count

    def get_alert_count(self) -> int:
        """Return the number of retained alerts, not only the recent page."""
        return len(self._alerts)

    def get_latest(self, sensor_id: Optional[str] = None) -> Optional[dict]:
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
                    if alert.timestamp is not None
                    and start_ts <= alert.timestamp <= end_ts
                ),
                key=self._alert_sort_key,
                reverse=True,
            )
        ]

    def get_snapshot_at(self, ts: float) -> dict:
        """获取指定时间点的传感器快照（取该时间点之前最近的一条数据）"""
        result = {}
        for sensor_id, readings in self._full_history.items():
            if not readings:
                continue
            index = bisect.bisect_right(
                readings,
                ts,
                key=lambda reading: reading.timestamp,
            ) - 1
            if index >= 0:
                result[sensor_id] = self._reading_to_dict(readings[index])
        return result

    def get_top_spikes(self) -> List[dict]:
        """获取 Top-K 峰值"""
        spikes = sorted(self._top_spikes, key=lambda x: x[0])
        return [
            {"value": -s[0], "sensor_id": s[1], "timestamp": s[2]}
            for s in spikes
        ]

    def get_stats(self, reference_time: Optional[float] = None) -> dict:
        """获取引擎统计信息"""
        elapsed = time.time() - self._start_time
        return {
            "total_readings": self._total_readings,
            "sensor_count": len(self._latest),
            "online_sensor_count": self.get_online_sensor_count(reference_time),
            "retained_alerts": len(self._alerts),
            "throughput": round(self._total_readings / elapsed, 1) if elapsed > 0 else 0,
            "uptime_seconds": round(elapsed, 1)
        }

    def _trim_reading_timestamps(self, sensor_id: str) -> None:
        timestamps = self._reading_timestamps.get(sensor_id)
        anchor = self._reading_retention_anchor
        if not timestamps or anchor is None:
            return
        cutoff = anchor - _READING_TIMESTAMP_RETENTION_SECONDS
        first_keep = bisect.bisect_left(timestamps, cutoff)
        if first_keep:
            del timestamps[:first_keep]

    @staticmethod
    def _alert_to_dict(alert: Alert) -> dict:
        return {
            "id": str(alert.id),
            "sensor_id": alert.sensor_id,
            "sensor_name": alert.sensor_name,
            "level": alert.level,
            "message": alert.message,
            "value": alert.value,
            "threshold": alert.threshold,
            "source": alert.source,
            "timestamp": alert.timestamp,
            "details": alert.details,
        }

    def _reading_to_dict(self, r: SensorReading) -> dict:
        return {
            "sensor_id": r.sensor_id,
            "name": r.name,
            "type": r.type,
            "value": r.value,
            "timestamp": r.timestamp
        }
