# -*- coding: utf-8 -*-
"""快速批量导入验证数据 - 大批次"""
import csv
from pathlib import Path
import json
import requests
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / 'data' / 'validation' / 'bridge_validation_data.csv'

API = 'http://localhost:8000/api/data/upload/json?push_live=false'
BATCH = 5000

def main():
    print("读取CSV...")
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S").timestamp()
            rows.append({
                "sensor_id": row["sensor_id"],
                "name": row["name"],
                "type": row["type"],
                "value": float(row["value"]),
                "timestamp": ts
            })

    print(f"共 {len(rows)} 条，分 {len(rows)//BATCH + 1} 批上传...")
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i+BATCH]
        r = requests.post(API, json=batch)
        print(f"  批次 {i//BATCH + 1}: {r.json()['records_ingested']} 条")

    print("✅ 导入完成！")

if __name__ == "__main__":
    main()
