"""
桥梁监测数据批量导入工具（零依赖版）
使用方法:
    1. 确保后端已启动 (双击 start_backend.bat)
    2. 默认读取 data/validation/bridge_validation_data.csv
    3. 修改下面的 CONFIG 配置
    4. 运行: py scripts/data/import_data.py

依赖: 只需要 requests (py -m pip install requests)
"""

import csv
import json
import os
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ====================== 配置区 ======================
CONFIG = {
    # 后端地址，一般不用改
    "api_url": "http://localhost:8000",

    # 你的CSV文件路径
    "csv_file": str(PROJECT_ROOT / "data" / "validation" / "bridge_validation_data.csv"),

    # CSV列名映射：左边是平台字段，右边是你的CSV列名
    # 如果你的CSV列名就是 sensor_id/name/type/value/timestamp 就不用改
    "column_mapping": {
        "sensor_id": "sensor_id",
        "name": "name",
        "type": "type",
        "value": "value",
        "timestamp": "timestamp"
    },

    # 如果你的CSV里没有sensor_id列，在这里指定所有数据属于哪个传感器
    # 比如: "default_sensor_id": "S01"
    "default_sensor_id": None,

    # 如果你的CSV里没有name列，自动根据sensor_id生成名称
    "auto_generate_name": True,

    # 如果你的CSV里没有type列，默认数据类型
    # 可选: strain(应变) / displacement(位移) / acceleration(加速度) / temperature(温度)
    "default_type": "strain",

    # 批量提交大小
    "batch_size": 100,

    # 提交间隔（秒）
    "submit_interval": 0.02,

    # 失败重试次数
    "max_retries": 3,
}

# 传感器信息表
SENSOR_INFO = {
    "S01": {"name": "主跨跨中-应变", "type": "strain"},
    "S02": {"name": "主跨1/4-应变", "type": "strain"},
    "S03": {"name": "索塔顶部-位移", "type": "displacement"},
    "S04": {"name": "拉索L01-加速度", "type": "acceleration"},
    "S05": {"name": "主跨跨中-挠度", "type": "displacement"},
    "S06": {"name": "索塔底部-应变", "type": "strain"},
    "S07": {"name": "拉索L02-加速度", "type": "acceleration"},
    "S08": {"name": "桥面温度", "type": "temperature"},
}


def check_backend():
    """检查后端是否启动"""
    try:
        r = requests.get(f"{CONFIG['api_url']}/api/health", timeout=5)
        if r.status_code == 200:
            info = r.json()
            print(f"✅ 后端连接成功!")
            print(f"   传感器在线: {info['sensor_count']}")
            print(f"   当前告警: {info['retained_alerts']}")
            return True
    except:
        pass
    print("❌ 无法连接后端，请先双击 start_backend.bat 启动后端")
    return False


def read_csv(file_path):
    """读取CSV文件"""
    print(f"\n📂 读取文件: {file_path}")

    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return None

    records = []
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        print(f"   CSV列名: {reader.fieldnames}")

        for row in reader:
            rec = {}

            # 字段映射
            for target_field, source_field in CONFIG["column_mapping"].items():
                if source_field in row and row[source_field].strip():
                    rec[target_field] = row[source_field].strip()

            # 默认sensor_id
            if CONFIG["default_sensor_id"] and "sensor_id" not in rec:
                rec["sensor_id"] = CONFIG["default_sensor_id"]

            # 必须有sensor_id和value
            if "sensor_id" not in rec or "value" not in rec:
                continue

            # 转换value为数字
            try:
                rec["value"] = float(rec["value"])
            except:
                continue

            # 自动生成name
            if CONFIG["auto_generate_name"] and "name" not in rec:
                sid = rec["sensor_id"]
                if sid in SENSOR_INFO:
                    rec["name"] = SENSOR_INFO[sid]["name"]
                else:
                    rec["name"] = f"传感器{sid}"

            # 默认type
            if "type" not in rec:
                sid = rec["sensor_id"]
                if sid in SENSOR_INFO:
                    rec["type"] = SENSOR_INFO[sid]["type"]
                else:
                    rec["type"] = CONFIG["default_type"]

            # 处理时间戳
            if "timestamp" in rec:
                try:
                    ts = float(rec["timestamp"])
                    if ts > 1e12:  # 毫秒转秒
                        ts = ts / 1000
                    rec["timestamp"] = ts
                except:
                    # 尝试解析日期字符串
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(rec["timestamp"].replace('Z', '+00:00'))
                        rec["timestamp"] = dt.timestamp()
                    except:
                        pass

            records.append(rec)

    print(f"   读取到有效数据: {len(records)} 条")

    # 统计传感器分布
    from collections import Counter
    counter = Counter(r["sensor_id"] for r in records)
    for sid, count in counter.most_common():
        print(f"   {sid}: {count} 条")

    return records


def import_data(records):
    """批量导入数据"""
    print(f"\n🚀 开始导入数据...")

    total = len(records)
    success = 0
    failed = 0
    total_alerts = 0

    for i in range(0, total, CONFIG["batch_size"]):
        batch = records[i:i+CONFIG["batch_size"]]

        for retry in range(CONFIG["max_retries"]):
            try:
                r = requests.post(
                    f"{CONFIG['api_url']}/api/data/upload/json",
                    json=batch,
                    timeout=10
                )
                if r.status_code == 200:
                    result = r.json()
                    success += len(batch)
                    total_alerts += result.get("alerts_triggered", 0)
                    progress = min(i+CONFIG["batch_size"], total)
                    print(f"   进度: {progress}/{total} ({progress*100//total}%) "
                          f"✅ 成功, 触发告警: {result.get('alerts_triggered', 0)}")
                    break
                else:
                    print(f"   批次 {i//CONFIG['batch_size']+1} 返回 {r.status_code}, 重试 {retry+1}...")
                    time.sleep(0.3)
            except Exception as e:
                print(f"   批次 {i//CONFIG['batch_size']+1} 错误: {str(e)[:50]}, 重试 {retry+1}...")
                time.sleep(0.3)
        else:
            failed += len(batch)
            print(f"   批次 {i//CONFIG['batch_size']+1} 最终失败")

        time.sleep(CONFIG["submit_interval"])

    print(f"\n📊 导入完成!")
    print(f"   总计: {total} 条")
    print(f"   成功: {success} 条")
    print(f"   失败: {failed} 条")
    print(f"   触发告警: {total_alerts} 条")

    return success, failed


def import_single_sensor(file_path, sensor_id, value_column,
                        time_column=None, sensor_type=None):
    """
    【最常用】导入单个传感器的CSV
    适合你的CSV只有时间戳+数值两列的情况

    参数:
        file_path: CSV文件路径
        sensor_id: 传感器ID (S01-S08)
        value_column: 数值列的列名
        time_column: 时间列的列名（可选，没有就用当前时间）
        sensor_type: 数据类型（可选，自动根据sensor_id判断）

    示例:
        import_single_sensor("应变数据.csv", "S01", "应变值(με)", "时间")
    """
    print(f"\n🚀 快速导入: {file_path} -> {sensor_id}")

    info = SENSOR_INFO.get(sensor_id, {"name": sensor_id, "type": "strain"})
    if sensor_type:
        info["type"] = sensor_type

    records = []
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                value = float(row[value_column])
            except:
                continue

            rec = {
                "sensor_id": sensor_id,
                "name": info["name"],
                "type": info["type"],
                "value": value,
            }

            if time_column and time_column in row:
                time_str = row[time_column].strip()
                try:
                    # 尝试解析数字时间戳
                    ts = float(time_str)
                    if ts > 1e12:
                        ts = ts / 1000
                    rec["timestamp"] = ts
                except:
                    # 尝试解析日期格式
                    try:
                        from datetime import datetime
                        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
                                    "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                            try:
                                dt = datetime.strptime(time_str, fmt)
                                rec["timestamp"] = dt.timestamp()
                                break
                            except:
                                pass
                    except:
                        pass

            records.append(rec)

    print(f"   读取到 {len(records)} 条数据")

    # 批量导入
    success = 0
    for i in range(0, len(records), CONFIG["batch_size"]):
        batch = records[i:i+CONFIG["batch_size"]]
        try:
            r = requests.post(f"{CONFIG['api_url']}/api/data/upload/json",
                            json=batch, timeout=10)
            if r.status_code == 200:
                success += len(batch)
                print(f"   进度: {min(i+CONFIG['batch_size'], len(records))}/{len(records)}")
        except Exception as e:
            print(f"   错误: {e}")
        time.sleep(0.02)

    print(f"✅ 导入完成: {success}/{len(records)} 条")
    return success


if __name__ == "__main__":
    print("=" * 55)
    print("   🌉 桥梁数字孪生平台 - 数据批量导入工具")
    print("=" * 55)

    # 检查依赖
    try:
        import requests
    except ImportError:
        print("❌ 缺少 requests 库，请先运行: py -m pip install requests")
        exit(1)

    if not check_backend():
        exit(1)

    if not os.path.exists(CONFIG["csv_file"]):
        print(f"\n⚠️  未找到配置文件: {CONFIG['csv_file']}")
        print(f"\n📝 使用方法:")
        print(f"1. 把你的CSV文件放到当前目录: {os.getcwd()}")
        print(f"2. 修改脚本开头 CONFIG 里的 csv_file 和 column_mapping")
        print(f"\n💡 最简单的用法（单传感器导入）:")
        print(f'   from import_data import import_single_sensor')
        print(f'   import_single_sensor("你的数据.csv", "S01", "数值列名")')
        exit(0)

    records = read_csv(CONFIG["csv_file"])
    if not records:
        print("❌ 没有有效数据")
        exit(1)

    input("\n按回车键开始导入...")
    import_data(records)

    # 验证
    try:
        r = requests.get(f"{CONFIG['api_url']}/api/sensors", timeout=5)
        if r.status_code == 200:
            print(f"\n📡 当前传感器状态:")
            for s in r.json():
                level_emoji = {"green": "🟢", "yellow": "🟡",
                              "orange": "🟠", "red": "🔴"}.get(s["level"], "⚪")
                print(f"   {level_emoji} {s['sensor_id']}: {s['name']} = "
                      f"{s['value']:.2f}")
    except:
        pass
