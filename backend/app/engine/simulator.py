"""
数据仿真器 - 模拟桥梁传感器数据流
生成8个传感器（应变计/位移计/加速度计/温度计）的实时数据
支持周期性异常注入和手动异常触发
传感器ID与前端3D位置一一对应
"""

import random
import threading
import time
from dataclasses import dataclass

import numpy as np

from app.sensor_ids import SensorIdentifier
from app.sensor_reading import SensorReadingRecord
from app.sensor_types import SensorType

AUTOMATIC_INJECTION_TARGET = SensorIdentifier("S01")
AUTOMATIC_MIN_MULTIPLIER = 2.5
AUTOMATIC_MAX_MULTIPLIER = 4.0
MIN_INJECTION_MULTIPLIER = 2.5
MAX_INJECTION_MULTIPLIER = 4.0
MIN_INJECTION_OFFSET = 50.0
MAX_INJECTION_OFFSET = 150.0


class UnknownSimulatorSensorError(LookupError):
    """Raised when an injection names a sensor the simulator does not emit."""


def _normalize_sensor_identifier(
    sensor_id: str | SensorIdentifier,
) -> SensorIdentifier:
    if isinstance(sensor_id, SensorIdentifier):
        return sensor_id
    try:
        return SensorIdentifier(sensor_id)
    except ValueError as exc:
        raise UnknownSimulatorSensorError(
            f"Sensor {sensor_id!r} not found"
        ) from exc


@dataclass(frozen=True, slots=True)
class SimulatorSensor:
    """Static identity and normal-behaviour configuration for one sensor."""

    identifier: SensorIdentifier
    name: str
    sensor_type: SensorType
    normal_mean: float
    normal_std: float


@dataclass(frozen=True)
class AnomalyInjection:
    """A one-shot anomaly transformation applied to one Sensor Reading."""

    sensor_id: SensorIdentifier
    multiplier: float
    offset: float

    def apply(self, normal_value: float) -> float:
        return normal_value * self.multiplier + self.offset


@dataclass(frozen=True, slots=True)
class SimulatorReading:
    """One typed reading emitted by a simulator sensor stream."""

    sensor_id: SensorIdentifier
    name: str
    type: SensorType
    value: float
    timestamp: float

    def to_dict(self) -> SensorReadingRecord:
        return {
            "sensor_id": self.sensor_id,
            "name": self.name,
            "type": self.type,
            "value": self.value,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class InjectedReading:
    """A generated target-sensor reading and the transform that produced it."""

    reading: SimulatorReading
    injection: AnomalyInjection


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
        SimulatorSensor(
            SensorIdentifier("S01"), "主跨跨中-应变", SensorType.STRAIN, 200, 30
        ),
        SimulatorSensor(
            SensorIdentifier("S02"), "主跨1/4-应变", SensorType.STRAIN, 150, 25
        ),
        SimulatorSensor(
            SensorIdentifier("S03"), "索塔顶部-位移", SensorType.DISPLACEMENT, 15, 4
        ),
        SimulatorSensor(
            SensorIdentifier("S04"), "拉索L01-加速度", SensorType.ACCELERATION, 0.5, 0.3
        ),
        SimulatorSensor(
            SensorIdentifier("S05"), "主跨跨中-挠度", SensorType.DISPLACEMENT, 20, 5
        ),
        SimulatorSensor(
            SensorIdentifier("S06"), "索塔底部-应变", SensorType.STRAIN, 180, 28
        ),
        SimulatorSensor(
            SensorIdentifier("S07"), "拉索L02-加速度", SensorType.ACCELERATION, 0.4, 0.25
        ),
        SimulatorSensor(
            SensorIdentifier("S08"), "桥面温度", SensorType.TEMPERATURE, 28, 3
        ),
    ]
    KNOWN_SENSOR_IDENTIFIERS = frozenset(
        sensor.identifier for sensor in SENSORS
    )

    def __init__(self):
        self.is_running = False
        self.tick = 0
        self._sensor_ticks: dict[SensorIdentifier, int] = {
            sensor.identifier: 0 for sensor in self.SENSORS
        }
        self.anomaly_inject_interval = 200  # 每200周期自动注入一次异常
        self._frame_lock = threading.Lock()

    def next_readings(self, timestamp: float | None = None) -> list[SensorReadingRecord]:
        """Generate one complete frame; concurrent callers own complete frames."""
        with self._frame_lock:
            self.tick += 1
            return self._build_readings(timestamp)

    def _build_readings(self, timestamp: float | None) -> list[SensorReadingRecord]:
        reading_timestamp = time.time() if timestamp is None else float(timestamp)
        return [
            self._next_reading_unlocked(
                sensor,
                reading_timestamp,
            ).to_dict()
            for sensor in self.SENSORS
        ]

    def _next_reading_unlocked(
        self,
        sensor: SimulatorSensor,
        timestamp: float | None,
        *,
        injection: AnomalyInjection | None = None,
    ) -> SimulatorReading:
        sensor_tick = self._sensor_ticks[sensor.identifier] + 1
        self._sensor_ticks[sensor.identifier] = sensor_tick
        normal_value = self._generate_normal_value(sensor, sensor_tick)
        value = normal_value

        if (
            injection is None
            and sensor.identifier == AUTOMATIC_INJECTION_TARGET
            and self.tick % self.anomaly_inject_interval == 0
        ):
            value = normal_value * random.uniform(
                AUTOMATIC_MIN_MULTIPLIER,
                AUTOMATIC_MAX_MULTIPLIER,
            )
            value += float(
                np.random.normal(0, sensor.normal_std * 0.5)
            )

        if injection is not None:
            value = injection.apply(normal_value)

        reading_timestamp = time.time() if timestamp is None else float(timestamp)
        return SimulatorReading(
            sensor_id=sensor.identifier,
            name=sensor.name,
            type=sensor.sensor_type,
            value=round(float(value), 4),
            timestamp=reading_timestamp,
        )

    def _validated_sensor_target(
        self,
        sensor_id: str | SensorIdentifier,
    ) -> SensorIdentifier:
        target = _normalize_sensor_identifier(sensor_id)
        if target not in self.KNOWN_SENSOR_IDENTIFIERS:
            raise UnknownSimulatorSensorError(
                f"Sensor {target!r} not found"
            )
        return target

    def _sensor_by_identifier(
        self,
        sensor_id: SensorIdentifier,
    ) -> SimulatorSensor:
        return next(
            sensor for sensor in self.SENSORS
            if sensor.identifier == sensor_id
        )

    @staticmethod
    def _generate_normal_value(
        sensor: SimulatorSensor,
        sensor_tick: int,
    ) -> float:
        value = float(
            np.random.normal(sensor.normal_mean, sensor.normal_std)
        )
        if sensor.sensor_type == SensorType.TEMPERATURE:
            hour_of_day = (sensor_tick % 86400) / 3600
            value += 8 * np.sin(2 * np.pi * (hour_of_day - 14) / 24)
        return value

    def inject_anomaly(
        self,
        sensor_id: str | SensorIdentifier,
        timestamp: float | None = None,
    ) -> InjectedReading:
        """Generate one injected reading for the requested sensor."""
        target = self._validated_sensor_target(sensor_id)

        with self._frame_lock:
            sensor = self._sensor_by_identifier(target)
            injection = self._create_injection(target)
            reading = self._next_reading_unlocked(
                sensor,
                timestamp,
                injection=injection,
            )
            return InjectedReading(
                reading=reading,
                injection=injection,
            )

    def _create_injection(
        self,
        sensor_id: SensorIdentifier,
    ) -> AnomalyInjection:
        return AnomalyInjection(
            sensor_id=sensor_id,
            multiplier=random.uniform(
                MIN_INJECTION_MULTIPLIER,
                MAX_INJECTION_MULTIPLIER,
            ),
            offset=random.uniform(
                MIN_INJECTION_OFFSET,
                MAX_INJECTION_OFFSET,
            ),
        )

    def stop(self):
        """停止仿真"""
        self.is_running = False
