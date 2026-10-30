import time

import pytest

from tests.factories import reading, sensor_records


def test_snapshot_returns_each_sensors_latest_reading_at_or_before_time(client):
    base = 1_700_000_000.0
    records = [
        reading(sensor_id="S01", value=10.0, timestamp=base + 10),
        reading(sensor_id="S01", value=20.0, timestamp=base + 20),
        reading(sensor_id="S02", value=5.0, timestamp=base + 5),
        reading(sensor_id="S02", value=15.0, timestamp=base + 15),
        reading(sensor_id="S03", value=30.0, timestamp=base + 30),
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    exact = client.get(
        "/api/sensors/history/snapshot", params={"ts": base + 20}
    )
    between = client.get(
        "/api/sensors/history/snapshot", params={"ts": base + 16}
    )
    before_any = client.get(
        "/api/sensors/history/snapshot", params={"ts": base + 4}
    )

    assert exact.status_code == 200
    assert {sensor_id: item["value"] for sensor_id, item in exact.json().items()} == {
        "S01": 20.0,
        "S02": 15.0,
    }
    assert {sensor_id: item["value"] for sensor_id, item in between.json().items()} == {
        "S01": 10.0,
        "S02": 15.0,
    }
    assert before_any.json() == {}


@pytest.mark.parametrize("ts", ["nan", "inf", "-inf"])
def test_snapshot_rejects_non_finite_timestamp(client, ts):
    response = client.get(
        "/api/sensors/history/snapshot",
        params={"ts": ts},
    )

    assert response.status_code == 400
    assert "finite" in str(response.json()).lower()


def test_snapshot_interface_stays_under_100ms_with_eight_full_histories(client, app):
    base = 1_700_000_000.0
    app.state.services.engine.ingest(
        sensor_records(
            base=base,
            sensor_count=8,
            sample_count=100_000,
        )
    )

    started = time.perf_counter()
    response = client.get(
        "/api/sensors/history/snapshot",
        params={"ts": base + 50_000},
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert len(response.json()) == 8
    assert elapsed <= 0.1


def test_24_hour_four_times_speed_replay_matches_snapshots_and_alerts(client, app):
    base = 1_700_000_000.0
    sample_interval = 10.0
    sample_count = 8_641

    def replay_value(sensor: int, index: int) -> float:
        if sensor == 0 and index % 360 == 0:
            return 600.0
        return float(100 + (sensor * 3 + index) % 10)

    records = sensor_records(
        base=base,
        sensor_count=8,
        sample_count=sample_count,
        sample_interval=sample_interval,
        value_for=replay_value,
    )
    for offset in range(0, len(records), 10_000):
        response = client.post(
            "/api/data/upload/json?push_live=false",
            json=records[offset : offset + 10_000],
        )
        assert response.status_code == 200

    playback_poll_interval = 60.0
    playback_speed = 4
    playback_step = playback_poll_interval * playback_speed
    for offset in range(0, 86_401, int(playback_step)):
        expected_index = int(offset // sample_interval)
        snapshot = client.get(
            "/api/sensors/history/snapshot",
            params={"ts": base + offset},
        )
        alerts = client.get(
            "/api/sensors/history/alerts",
            params={"start": base, "end": base + offset},
        )

        assert snapshot.status_code == 200
        assert alerts.status_code == 200
        assert {
            sensor_id: item["value"]
            for sensor_id, item in snapshot.json().items()
        } == {
            f"S{sensor}": replay_value(sensor, expected_index)
            for sensor in range(8)
        }

        expected_rule_alert_count = offset // 3_600 + 1
        alert_payload = alerts.json()
        assert alert_payload["start"] == base
        assert alert_payload["end"] == base + offset
        rule_alerts = [
            item for item in alert_payload["alerts"] if item["source"] == "rule"
        ]
        engine_alerts = app.state.services.engine.get_alerts_range(
            base,
            base + offset,
        )
        assert alert_payload["count"] == len(engine_alerts)
        assert len(rule_alerts) == expected_rule_alert_count
        assert [
            (
                item["timestamp"],
                item["sensor_id"],
                item["sensor_name"],
                item["level"],
                item["value"],
                item["threshold"],
                item["source"],
            )
            for item in rule_alerts
        ] == [
            (
                base + index * 3_600,
                "S0",
                "Sensor 0",
                "red",
                600.0,
                600.0,
                "rule",
            )
            for index in range(expected_rule_alert_count - 1, -1, -1)
        ]


def test_replay_returns_empty_results_before_any_data(client):
    snapshot = client.get(
        "/api/sensors/history/snapshot",
        params={"ts": 1_700_000_000.0},
    )
    alerts = client.get(
        "/api/sensors/history/alerts",
        params={"start": 1_700_000_000.0, "end": 1_700_000_100.0},
    )

    assert snapshot.status_code == 200
    assert snapshot.json() == {}
    assert alerts.status_code == 200
    assert alerts.json()["count"] == 0
    assert alerts.json()["alerts"] == []


def test_replay_handles_huge_finite_time_bounds(client):
    base = 1_700_000_000.0
    records = [
        reading(sensor_id=f"HUGE{index}", value=600.0, timestamp=base + index)
        for index in range(3)
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    snapshot = client.get(
        "/api/sensors/history/snapshot",
        params={"ts": 1e308},
    )
    alerts = client.get(
        "/api/sensors/history/alerts",
        params={"start": -1e308, "end": 1e308},
    )

    assert snapshot.status_code == 200
    assert set(snapshot.json()) == {"HUGE0", "HUGE1", "HUGE2"}
    assert alerts.status_code == 200
    assert alerts.json()["count"] == 3
    assert [item["sensor_id"] for item in alerts.json()["alerts"]] == [
        "HUGE2",
        "HUGE1",
        "HUGE0",
    ]
