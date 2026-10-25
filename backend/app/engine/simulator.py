"""
数据仿真器 - 模拟桥梁传感器数据流
生成8个传感器（应变计/位移计/加速度计/温度计）的实时数据
支持周期性异常注入和手动异常触发
传感器ID与前端3D位置一一对应
"""

import asyncio
import numpy as np
import time
import random


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

    def __init__(self):
        self.is_running = False
        self.tick = 0
        self.anomaly_inject_interval = 200  # 每200周期自动注入一次异常
        self.manual_anomaly = False
        self.anomaly_sensor = None

    async def generate(self):
        """
        异步生成器：每秒产生一组传感器数据
        """
        self.is_running = True
        while self.is_running:
            self.tick += 1
            data = []

            for sensor in self.SENSORS:
                mean = sensor["normal_mean"]
                std = sensor["normal_std"]
                value = np.random.normal(mean, std)

                # 自动异常注入：每200周期在S01注入应变突增
                if self.tick % self.anomaly_inject_interval == 0 and sensor["id"] == "S01":
                    value = mean * (2.5 + random.random() * 1.5)
                    value += np.random.normal(0, std * 0.5)

                # 手动异常注入
                if self.manual_anomaly and self.anomaly_sensor and sensor["id"] == self.anomaly_sensor:
                    if sensor["type"] == "strain":
                        value = mean * (3.0 + random.random() * 2.0)
                    elif sensor["type"] == "displacement":
                        value = mean * (4.0 + random.random() * 3.0)
                    elif sensor["type"] == "acceleration":
                        value = mean * (5.0 + random.random() * 5.0)
                    elif sensor["type"] == "temperature":
                        value = mean + 30 + random.random() * 10

                # 温度日变化
                if sensor["type"] == "temperature":
                    hour_of_day = (self.tick % 86400) / 3600
                    value += 8 * np.sin(2 * np.pi * (hour_of_day - 14) / 24)

                data.append({
                    "sensor_id": sensor["id"],
                    "name": sensor["name"],
                    "type": sensor["type"],
                    "value": round(float(value), 4),
                    "timestamp": time.time()
                })

            self.manual_anomaly = False
            self.anomaly_sensor = None

            yield data
            await asyncio.sleep(1)

    def inject_anomaly(self, sensor_id: str = "S01"):
        """手动注入异常"""
        self.manual_anomaly = True
        self.anomaly_sensor = sensor_id

    def stop(self):
        """停止仿真"""
        self.is_running = False
