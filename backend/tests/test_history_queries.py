import time

import pytest
from app.engine.data_engine import MonitoringEngine
from app.sensor_batch import SensorBatch


@pytest.mark.parametrize(
    ("params", "expected_detail"),
    [
        (
            {"sensor_id": "S01", "start": 10, "end": 5, "max_points": 100},
            "start",
        ),
        (
            {"sensor_id": "S01", "start": 5, "end": 10, "max_points": 9},
            "max_points",
        ),
        (
            {"sensor_id": "S01", "start": 5, "end": 10, "max_points": 5001},
            "max_points",
        ),
    ],
)
def test_history_range_rejects_invalid_bounds_and_limits(client, params, expected_detail):
    response = client.get("/api/sensors/history/range", params=params)

    assert response.status_code == 400
    assert expected_detail in str(response.json()).lower()


def reading(value: float, timestamp: float, sensor_id: str = "S01") -> dict:
    return {
        "sensor_id": sensor_id,
        "name": "Main span strain",
        "type": "strain",
        "value": value,
        "timestamp": timestamp,
    }


def test_stats_describe_retained_rolling_window(client):
    records = [
        reading(value=float(index), timestamp=1_700_000_000.0 + index)
        for index in range(600)
    ]

    upload = client.post("/api/data/upload/json?push_live=false", json=records)
    stats = client.get("/api/sensors/S01/stats")

    assert upload.status_code == 200
    assert stats.status_code == 200
    assert stats.json() == {
        "sensor_id": "S01",
        "count": 500,
        "mean": 349.5,
        "max": 599.0,
        "min": 100.0,
        "latest": 599.0,
    }
@pytest.mark.parametrize("minutes", [0, 1441])
def test_recent_history_rejects_minutes_outside_supported_range(client, minutes):
    response = client.get("/api/sensors/S01/history", params={"minutes": minutes})

    assert response.status_code == 400
    assert "minutes" in str(response.json()).lower()
def test_rolling_window_evicts_in_fifo_order(client):
    base = time.time() - 1000
    records = [
        reading(value=float(index), timestamp=base + index)
        for index in range(501)
    ]
    late_old_reading = reading(value=-1.0, timestamp=base - 1)

    assert client.post("/api/data/upload/json?push_live=false", json=records).status_code == 200
    assert client.post(
        "/api/data/upload/json?push_live=false", json=[late_old_reading]
    ).status_code == 200

    response = client.get("/api/sensors/S01/history", params={"minutes": 1440})

    assert response.status_code == 200
    timestamps = [item["timestamp"] for item in response.json()["data"]]
    assert len(timestamps) == 500
    assert timestamps == [base - 1, *[base + index for index in range(2, 501)]]

def test_full_history_evicts_oldest_timestamp_and_stays_queryable():
    engine = MonitoringEngine()
    records = [
        reading(value=float(index), timestamp=100_000.0 - index)
        for index in range(100_001)
    ]

    engine.ingest(SensorBatch(records=records))
    data = engine.get_history_range("S01", 0.0, 100_000.0, 5000)

    assert len(data) == 5000
    assert data[0]["timestamp"] == 1.0
    assert data[-1]["timestamp"] == 100_000.0
    assert engine.get_time_range()["start"] == 1.0
@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/sensors/history/range", {"sensor_id": "S01", "start": "bad", "end": 10}),
        ("/api/sensors/history/range", {"sensor_id": "S01", "start": 0, "end": 10, "max_points": "bad"}),
        ("/api/sensors/S01/history", {"minutes": "bad"}),
    ],
)
def test_history_query_type_errors_are_reported_as_400(client, path, params):
    response = client.get(path, params=params)

    assert response.status_code == 400
    assert "detail" in response.json()
@pytest.mark.parametrize(
    ("start", "end"),
    [("nan", 10), ("-inf", 10), (0, "inf")],
)
def test_history_range_rejects_non_finite_timestamps(client, start, end):
    response = client.get(
        "/api/sensors/history/range",
        params={"sensor_id": "S01", "start": start, "end": end},
    )

    assert response.status_code == 400
    assert "finite" in str(response.json()).lower()
def test_86400_record_history_range_matches_source_data(client):
    base = 1_700_000_000.0
    records = [
        reading(value=(index % 100) / 10.0, timestamp=base + index)
        for index in range(86_400)
    ]
    expected_by_timestamp = {item["timestamp"]: item for item in records}

    for offset in range(0, len(records), 10_000):
        response = client.post(
            "/api/data/upload/json?push_live=false",
            json=records[offset : offset + 10_000],
        )
        assert response.status_code == 200

    time_range = client.get("/api/sensors/history/timerange")
    response = client.get(
        "/api/sensors/history/range",
        params={
            "sensor_id": "S01",
            "start": base,
            "end": base + 86_399,
            "max_points": 5000,
        },
    )

    assert time_range.status_code == 200
    assert time_range.json() == {
        "start": base,
        "end": base + 86_399,
        "has_data": True,
    }
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 5000
    assert payload["data"][0]["timestamp"] == base
    assert payload["data"][-1]["timestamp"] == base + 86_399
    assert [item["timestamp"] for item in payload["data"]] == sorted(
        item["timestamp"] for item in payload["data"]
    )
    assert all(
        item == expected_by_timestamp[item["timestamp"]] for item in payload["data"]
    )
def test_history_range_includes_boundaries_and_downsampling_is_even(client):
    records = [
        reading(value=float(index), timestamp=1_700_000_000.0 + index)
        for index in range(100)
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    bounded = client.get(
        "/api/sensors/history/range",
        params={
            "sensor_id": "S01",
            "start": 1_700_000_010.0,
            "end": 1_700_000_020.0,
            "max_points": 11,
        },
    )
    sampled = client.get(
        "/api/sensors/history/range",
        params={
            "sensor_id": "S01",
            "start": 1_700_000_000.0,
            "end": 1_700_000_099.0,
            "max_points": 10,
        },
    )

    assert [item["timestamp"] for item in bounded.json()["data"]] == [
        1_700_000_000.0 + index for index in range(10, 21)
    ]
    assert [item["timestamp"] for item in sampled.json()["data"]] == [
        1_700_000_000.0 + index for index in range(0, 100, 11)
    ]



def test_downsampling_selects_points_uniformly_across_time(client):
    base = 1_700_000_000.0
    offsets = [*range(11), *range(100, 1000, 100)]
    records = [
        reading(value=float(index), timestamp=base + offset)
        for index, offset in enumerate(offsets)
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    response = client.get(
        "/api/sensors/history/range",
        params={
            "sensor_id": "S01",
            "start": base,
            "end": base + 900,
            "max_points": 10,
        },
    )

    assert response.status_code == 200
    assert [item["timestamp"] for item in response.json()["data"]] == [
        base + offset for offset in range(0, 1000, 100)
    ]
