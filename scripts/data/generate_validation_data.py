# -*- coding: utf-8 -*-
"""
生成桥梁健康监测验证数据（带损伤工况）
基于Z24桥和浍河大桥参数，包含正常状态、温度影响、车辆荷载和3次损伤事件
"""
import csv
from pathlib import Path
import math
import random
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_FILE = PROJECT_ROOT / 'data' / 'validation' / 'bridge_validation_data.csv'

random.seed(42)  # 固定随机种子，结果可复现

# 传感器配置
SENSORS = [
    {"id": "S01", "name": "主跨跨中-应变", "type": "strain", "base": 200, "noise": 25, "daily_amp": 40},
    {"id": "S02", "name": "主跨1/4跨-应变", "type": "strain", "base": 150, "noise": 20, "daily_amp": 30},
    {"id": "S03", "name": "右索塔塔顶-位移", "type": "displacement", "base": 15, "noise": 3, "daily_amp": 5},
    {"id": "S04", "name": "拉索L01-加速度", "type": "acceleration", "base": 0.5, "noise": 0.25, "daily_amp": 0.1},
    {"id": "S05", "name": "主跨跨中-挠度", "type": "displacement", "base": 20, "noise": 4, "daily_amp": 6},
    {"id": "S06", "name": "右索塔塔底-应变", "type": "strain", "base": 180, "noise": 22, "daily_amp": 35},
    {"id": "S07", "name": "拉索L02-加速度", "type": "acceleration", "base": 0.4, "noise": 0.2, "daily_amp": 0.08},
    {"id": "S08", "name": "桥面-温度", "type": "temperature", "base": 28, "noise": 0.8, "daily_amp": 5},
]

# 时间配置：24小时，每10秒一条
START_TIME = datetime(2026, 8, 13, 0, 0, 0)
DURATION_HOURS = 24
INTERVAL_SECONDS = 10
TOTAL_STEPS = int(DURATION_HOURS * 3600 / INTERVAL_SECONDS)

# 损伤工况（小时:分钟，传感器ID，异常倍数，持续分钟数）
DAMAGE_EVENTS = [
    # 第一次：第6小时，S01应变小幅突增（小损伤，黄色预警）
    {"start_hour": 6, "duration_min": 30, "sensor": "S01", "factor": 1.8, "offset": 100, "desc": "跨中应变异常"},
    # 第二次：第12小时，S03位移持续偏移（中损伤，橙色预警）
    {"start_hour": 12, "duration_min": 60, "sensor": "S03", "factor": 2.5, "offset": 20, "desc": "塔顶位移偏移"},
    # 第三次：第18小时，多传感器异常（大损伤，红色预警）
    {"start_hour": 18, "duration_min": 45, "sensor": "S01", "factor": 3.2, "offset": 250, "desc": "跨中严重应变"},
    {"start_hour": 18, "duration_min": 45, "sensor": "S04", "factor": 4.0, "offset": 2.0, "desc": "拉索异常振动"},
    {"start_hour": 18, "duration_min": 45, "sensor": "S05", "factor": 2.8, "offset": 40, "desc": "跨中挠度超标"},
]

def is_in_damage_event(step, sensor_id):
    """检查当前时间点是否在损伤事件中"""
    current_hour = step * INTERVAL_SECONDS / 3600
    for event in DAMAGE_EVENTS:
        if event["sensor"] != sensor_id:
            continue
        start = event["start_hour"]
        end = start + event["duration_min"] / 60
        if start <= current_hour < end:
            # 损伤有个渐变过程，前10%时间线性上升
            progress = (current_hour - start) / (end - start)
            ramp = min(1.0, progress / 0.1)
            return event["factor"] * ramp, event["offset"] * ramp
    return None, None

def generate_value(sensor, step):
    """生成单个传感器在某一时刻的值"""
    t = step * INTERVAL_SECONDS
    hour_of_day = (t / 3600) % 24

    # 日变化（温度引起的正弦波动，下午14点最高）
    daily = sensor["daily_amp"] * math.sin((hour_of_day - 8) / 24 * 2 * math.pi)

    # 基础值+日变化+噪声
    value = sensor["base"] + daily + random.gauss(0, sensor["noise"])

    # 随机车辆荷载（5%概率出现脉冲）
    if random.random() < 0.05:
        if sensor["type"] == "strain":
            value += random.uniform(20, 80)
        elif sensor["type"] == "displacement" and "加速度" not in sensor["name"]:
            value += random.uniform(2, 8)
        elif sensor["type"] == "acceleration":
            value += random.uniform(0.3, 1.0)

    # 应用损伤事件
    factor, offset = is_in_damage_event(step, sensor["id"])
    if factor is not None:
        value = value * factor + offset

    # 加速度取绝对值（振动幅值）
    if sensor["type"] == "acceleration":
        value = abs(value)

    # 温度不能低于15度
    if sensor["type"] == "temperature":
        value = max(15, value)

    return round(value, 3)

def main():
    output_file = OUTPUT_FILE
    output_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"正在生成验证数据：{DURATION_HOURS}小时，每{INTERVAL_SECONDS}秒一条...")

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["sensor_id", "name", "type", "value", "timestamp"])

        count = 0
        for step in range(TOTAL_STEPS):
            ts = START_TIME + timedelta(seconds=step * INTERVAL_SECONDS)
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            for sensor in SENSORS:
                value = generate_value(sensor, step)
                writer.writerow([sensor["id"], sensor["name"], sensor["type"], value, ts_str])
                count += 1

            if step % 1000 == 0:
                print(f"  进度: {step}/{TOTAL_STEPS} ({step*100//TOTAL_STEPS}%)")

    print(f"\n✅ 生成完成！共 {count} 条数据，保存到 {output_file}")
    print(f"   包含3次损伤工况：")
    print(f"   - 06:00 跨中应变异常（黄色预警）")
    print(f"   - 12:00 塔顶位移偏移（橙色预警）")
    print(f"   - 18:00 多传感器严重异常（红色预警）")

if __name__ == "__main__":
    main()
