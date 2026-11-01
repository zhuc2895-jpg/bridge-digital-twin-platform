"""Smoke-test the JSON upload and latest-state APIs."""

import json
import time
import urllib.request

now = time.time()
data = json.dumps(
    [
        {"sensor_id": "S01", "name": "主跨跨中-应变", "type": "strain", "value": 250.5, "timestamp": now},
        {"sensor_id": "S02", "name": "主跨1/4-应变", "type": "strain", "value": 180.2, "timestamp": now},
        {"sensor_id": "S03", "name": "索塔顶部-位移", "type": "displacement", "value": 15.3, "timestamp": now},
        {"sensor_id": "S04", "name": "拉索L01-加速度", "type": "acceleration", "value": 0.85, "timestamp": now},
        {"sensor_id": "S05", "name": "主跨跨中-挠度", "type": "displacement", "value": 22.1, "timestamp": now},
        {"sensor_id": "S06", "name": "索塔底部-应变", "type": "strain", "value": 320.8, "timestamp": now},
        {"sensor_id": "S07", "name": "拉索L02-加速度", "type": "acceleration", "value": 1.25, "timestamp": now},
        {"sensor_id": "S08", "name": "桥面温度", "type": "temperature", "value": 28.6, "timestamp": now},
    ]
).encode()

request = urllib.request.Request(
    "http://localhost:8000/api/data/upload/json?push_live=false",
    data=data,
    headers={"Content-Type": "application/json"},
)
response = urllib.request.urlopen(request)
print("JSON upload:", response.read().decode())

response = urllib.request.urlopen("http://localhost:8000/api/sensors/")
sensors = json.loads(response.read().decode())
print(f"\n传感器数量: {len(sensors)}")
for sensor_id, info in sensors.items():
    print(f"  {sensor_id}: {info['name']} = {info['value']} ({info['type']})")

response = urllib.request.urlopen("http://localhost:8000/api/alerts/")
payload = json.loads(response.read().decode())
alerts = payload["alerts"]
print(f"\n告警数量: {len(alerts)}")
for alert in alerts:
    print(f"  {alert['level'].upper()}: {alert['message']}")
