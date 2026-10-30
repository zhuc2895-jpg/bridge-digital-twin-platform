"""
数据仿真器 - 模拟桥梁传感器数据流
生成8个传感器（应变计/位移计/加速度计/温度计）的实时数据
支持周期性异常注入和手动异常触发
传感器ID与前端3D位置一一对应
"""

import asyncio
from collections import deque
from dataclasses import dataclass
import random
import threading
import time

import numpy as np

DEFAULT_INJECTION_SENSOR_ID = "S01"
MIN_INJECTION_MULTIPLIER = 2.5
MAX_INJECTION_MULTIPLIER = 4.0
MIN_INJECTION_OFFSET = 50.0
MAX_INJECTION_OFFSET = 150.0


class UnknownSimulatorSensorError(LookupError):
    """Raised when an injection names a sensor the simulator does not emit."""


@dataclass(frozen=True)
class AnomalyInjection:
    """One queued, single-reading anomaly transformation."""

    sensor_id: str
    multiplier: float
    offset: float

    def apply(self, normal_value: float) -> float:
        return normal_value * self.multiplier + self.offset


class DataSimulator:
    """
    模拟大跨径斜拉桥关键构件的传感器数据
    传感器布局与前端Three.js 3D位置对应:
    S01: 主跨跨中-应变    (0,4,0)
    S02: 主跨1/4-应变     (-30,4,0)
    S03: 索塔顶部-位移    (60,50,0) 右塔
    S04: 拉索L01-加速度   (-45,20,0)
    S05: 主跨跨中-挠度    (0,3.5,5)
    S06: 索塔底部-应变    (60,2,0) 右塔底
    S07: 拉索L02-加速度   (45,20,0)
    S08: 桥面温度         (0,5,-6)
    """

    SENSORS = [
        {"id": "S01", "name": "主跨跨中-应变", "type": "strain",
         "normal_mean": 200, "normal_std": 30},
        {"id": "S02", "name": "主跨1/4-应变", "type": "strain",
         "normal_mean": 150, "normal_std": 25},
        {"id": "S03", "name": "索塔顶部-位移", "type": "displacement",
         "normal_mean": 15, "normal_std": 4},
        {"id": "S04", "name": "拉索L01-加速度", "type": "acceleration",
         "normal_mean": 0.5, "normal_std": 0.3},
        {"id": "S05", "name": "主跨跨中-挠度", "type": "displacement",
         "normal_mean": 20, "normal_std": 5},
        {"id": "S06", "name": "索塔底部-应变", "type": "strain",
         "normal_mean": 180, "normal_std": 28},
        {"id": "S07", "name": "拉索L02-加速度", "type": "acceleration",
         "normal_mean": 0.4, "normal_std": 0.25},
        {"id": "S08", "name": "桥面温度", "type": "temperature",
         "normal_mean": 28, "normal_std": 3},
    ]
    SENSOR_IDS = frozenset(sensor["id"] for sensor in SENSORS)

    def __init__(self):
        self.is_running = False
        self.tick = 0
        self.anomaly_inject_interval = 200  # 每200周期自动注入一次异常
        self._pending_injections: dict[str, deque[AnomalyInjection]] = {}
        self._injection_lock = threading.Lock()
        self._frame_lock = threading.Lock()

    async def generate(self):
        """
        异步生成器：每秒产生一组传感器数据
        """
        self.is_running = True
        while self.is_running:
            yield self.next_readings()
            await asyncio.sleep(1)

    def next_readings(self, timestamp: float | None = None) -> list[dict]:
        """Generate one complete frame; concurrent callers own complete frames."""
        with self._frame_lock:
            return self._build_readings(timestamp)

    def _build_readings(self, timestamp: float | None) -> list[dict]:
        self.tick += 1
        reading_timestamp = time.time() if timestamp is None else float(timestamp)
        readings = []

        for sensor in self.SENSORS:
            normal_value = self._sample_normal_value(sensor)
            value = normal_value

            # 自动异常注入：每200周期在S01注入应变突增
            if self.tick % self.anomaly_inject_interval == 0 and sensor["id"] == "S01":
                value = normal_value * (2.5 + random.random() * 1.5)
                value += float(np.random.normal(0, sensor["normal_std"] * 0.5))

            injection = self._consume_injection(sensor["id"])
            if injection is not None:
                value = injection.apply(normal_value)

            readings.append({
                "sensor_id": sensor["id"],
                "name": sensor["name"],
                "type": sensor["type"],
                "value": round(float(value), 4),
                "timestamp": reading_timestamp,
            })

        return readings

    def _sample_normal_value(self, sensor: dict) -> float:
        value = float(
            np.random.normal(sensor["normal_mean"], sensor["normal_std"])
        )
        if sensor["type"] == "temperature":
            hour_of_day = (self.tick % 86400) / 3600
            value += 8 * np.sin(2 * np.pi * (hour_of_day - 14) / 24)
        return value

    def inject_anomaly(
        self,
        sensor_id: str = DEFAULT_INJECTION_SENSOR_ID,
    ) -> AnomalyInjection:
        """Queue exactly one injected reading for a known simulator sensor."""
        normalized_id = sensor_id.strip()
        if normalized_id not in self.SENSOR_IDS:
            raise UnknownSimulatorSensorError(
                f"Sensor {normalized_id or sensor_id!r} not found"
            )

        with self._injection_lock:
            injection = AnomalyInjection(
                sensor_id=normalized_id,
                multiplier=random.uniform(
                    MIN_INJECTION_MULTIPLIER,
                    MAX_INJECTION_MULTIPLIER,
                ),
                offset=random.uniform(
                    MIN_INJECTION_OFFSET,
                    MAX_INJECTION_OFFSET,
                ),
            )
            self._pending_injections.setdefault(
                normalized_id,
                deque(),
            ).append(injection)
            return injection

    def _consume_injection(self, sensor_id: str) -> AnomalyInjection | None:
        with self._injection_lock:
            pending = self._pending_injections.get(sensor_id)
            if not pending:
                return None
            injection = pending.popleft()
            if not pending:
                del self._pending_injections[sensor_id]
            return injection

    def pending_injection_count(self, sensor_id: str | None = None) -> int:
        """Return queued injection count for one sensor or the whole simulator."""
        with self._injection_lock:
            if sensor_id is not None:
                return len(self._pending_injections.get(sensor_id, ()))
            return sum(
                len(pending)
                for pending in self._pending_injections.values()
            )

    def stop(self):
        """停止仿真"""
        self.is_running = False
