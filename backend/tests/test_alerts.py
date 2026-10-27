import uuid

import pytest

from app.engine.data_engine import Alert
from tests.factories import reading


def test_same_level_alert_is_cooled_down_for_ten_seconds(client):
    base = 1_700_000_000.0

    first = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=600.0, timestamp=base)],
    )
    during_cooldown = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=610.0, timestamp=base + 5)],
    )
    after_cooldown = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=620.0, timestamp=base + 10)],
    )

    assert first.json()["alerts_triggered"] == 1
    assert during_cooldown.json()["alerts_triggered"] == 0
    assert after_cooldown.json()["alerts_triggered"] == 1
    alerts = client.get("/api/alerts/").json()["alerts"]
    assert len(alerts) == 2
    assert len({alert["id"] for alert in alerts}) == 2


def test_alert_lifecycle_uses_uuid_and_cross_source_cooldown(app, client):
    engine = app.state.services.engine
    base = 1_700_000_000.0

    first = engine.submit_alert(
        sensor_id="S01",
        sensor_name="Main span strain",
        level="red",
        message="threshold exceeded",
        value=600.0,
        threshold=600.0,
        source="rule",
        timestamp=base,
    )
    during_cooldown = engine.submit_alert(
        sensor_id="S01",
        sensor_name="Main span strain",
        level="red",
        message="AI anomaly confirmed",
        value=610.0,
        threshold=0.0,
        source="ai_dual_confirm",
        timestamp=base + 5,
    )
    after_cooldown = engine.submit_alert(
        sensor_id="S01",
        sensor_name="Main span strain",
        level="red",
        message="AI anomaly confirmed",
        value=620.0,
        threshold=0.0,
        source="ai_dual_confirm",
        timestamp=base + 10,
    )

    alerts = client.get("/api/alerts/").json()["alerts"]

    assert first is not None
    assert during_cooldown is None
    assert after_cooldown is not None
    assert [alert["source"] for alert in alerts] == ["ai_dual_confirm", "rule"]
    assert len({alert["id"] for alert in alerts}) == 2
    for alert in alerts:
        alert_id = uuid.UUID(alert["id"])
        assert alert_id.version == 4
        assert alert_id.variant == uuid.RFC_4122


def test_temperature_thresholds_can_be_read_changed_and_take_effect(client):
    defaults = client.get("/api/data/config/thresholds")
    update = client.post(
        "/api/data/config/thresholds",
        params={
            "temperature_yellow": 20,
            "temperature_orange": 25,
            "temperature_red": 30,
        },
    )
    readback = client.get("/api/data/config/thresholds")
    upload = client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(
                sensor_id="T01",
                name="Deck temperature",
                sensor_type="temperature",
                value=30.0,
                timestamp=1_700_000_000.0,
            )
        ],
    )

    assert defaults.status_code == 200
    assert defaults.json()["temperature"] == {
        "yellow": 45,
        "orange": 55,
        "red": 65,
    }
    assert update.status_code == 200
    assert update.json()["updated"] == {
        "temperature_yellow": 20.0,
        "temperature_orange": 25.0,
        "temperature_red": 30.0,
    }
    assert readback.json()["temperature"] == {
        "yellow": 20.0,
        "orange": 25.0,
        "red": 30.0,
    }
    assert upload.json()["alerts_triggered"] == 1
    alert = client.get("/api/alerts/").json()["alerts"][0]
    assert alert["level"] == "red"
    assert alert["threshold"] == 30.0
@pytest.mark.parametrize(
    ("sensor_type", "levels"),
    [
        ("strain", {"yellow": 300.0, "orange": 450.0, "red": 600.0}),
        ("displacement", {"yellow": 30.0, "orange": 50.0, "red": 80.0}),
        ("acceleration", {"yellow": 2.0, "orange": 3.5, "red": 5.0}),
        ("temperature", {"yellow": 45.0, "orange": 55.0, "red": 65.0}),
    ],
)
def test_all_sensor_threshold_boundaries_emit_only_highest_level(
    client, sensor_type, levels
):
    records = []
    expected = []
    for index, (level, threshold) in enumerate(levels.items()):
        sensor_id = f"{sensor_type}-{level}"
        value = -threshold if index == 0 else threshold
        records.append(
            reading(
                sensor_id=sensor_id,
                name=f"{sensor_type} {level}",
                sensor_type=sensor_type,
                value=value,
                timestamp=1_700_000_000.0 + index,
            )
        )
        expected.append((sensor_id, level, threshold))
    records.append(
        reading(
            sensor_id=f"{sensor_type}-normal",
            name=f"{sensor_type} normal",
            sensor_type=sensor_type,
            value=levels["yellow"] - 0.01,
            timestamp=1_700_000_010.0,
        )
    )

    response = client.post("/api/data/upload/json?push_live=false", json=records)
    alerts = client.get("/api/alerts/").json()["alerts"]

    assert response.json()["alerts_triggered"] == 3
    assert len(alerts) == 3
    assert len({alert["id"] for alert in alerts}) == 3
    assert {
        (alert["sensor_id"], alert["level"], alert["threshold"])
        for alert in alerts
    } == set(expected)
    assert all(alert["source"] == "rule" for alert in alerts)
    assert all(alert["sensor_name"] for alert in alerts)
    assert all(alert["message"] for alert in alerts)
    assert all(alert["timestamp"] >= 1_700_000_000.0 for alert in alerts)
def test_alert_stats_use_canonical_levels_and_sources(app, client):
    engine = app.state.services.engine
    base = 1_700_000_000.0
    for sensor_id, source in (
        ("S-RULE", "rule"),
        ("S-AI", "ai_stalwart"),
    ):
        engine.submit_alert(
            sensor_id=sensor_id,
            sensor_name=sensor_id,
            level="orange",
            message="anomaly",
            value=10.0,
            threshold=5.0,
            source=source,
            timestamp=base,
        )

    stats = client.get("/api/alerts/stats").json()

    assert set(stats["by_level"]) == {"yellow", "orange", "red"}
    assert stats["by_level"]["orange"] == 2
    assert set(stats["by_source"]) == {
        "rule",
        "ai_stalwart",
        "ai_gan_ae",
        "ai_isolation_forest",
        "ai_dual_confirm",
        "ai_feature_arbitration",
    }
    assert stats["by_source"]["rule"] == 1
    assert stats["by_source"]["ai_stalwart"] == 1
    assert stats["by_source"]["ai_gan_ae"] == 0


def test_same_event_time_alerts_use_detection_order(app, client):
    engine = app.state.services.engine
    timestamp = 1_700_000_000.0
    for sensor_id in ("S-A", "S-B", "S-C"):
        engine.submit_alert(
            sensor_id=sensor_id,
            sensor_name=sensor_id,
            level="red",
            message="anomaly",
            value=600.0,
            threshold=600.0,
            source="rule",
            timestamp=timestamp,
        )

    recent = client.get("/api/alerts/").json()["alerts"]
    ranged = client.get(
        "/api/sensors/history/alerts",
        params={"start": timestamp, "end": timestamp},
    ).json()["alerts"]

    assert [alert["sensor_id"] for alert in recent] == ["S-C", "S-B", "S-A"]
    assert [alert["sensor_id"] for alert in ranged] == ["S-C", "S-B", "S-A"]


def test_recent_alerts_are_limited_to_twenty_and_newest_first(client):
    records = [
        reading(
            sensor_id=f"S{index:02d}",
            name=f"Sensor {index}",
            value=600.0,
            timestamp=1_700_000_000.0 + index,
        )
        for index in range(25)
    ]

    upload = client.post("/api/data/upload/json?push_live=false", json=records)
    recent = client.get("/api/alerts/")

    assert upload.json()["alerts_triggered"] == 25
    assert recent.status_code == 200
    alerts = recent.json()["alerts"]
    assert len(alerts) == 20
    assert [alert["sensor_id"] for alert in alerts] == [
        f"S{index:02d}" for index in range(24, 4, -1)
    ]
    assert [alert["timestamp"] for alert in alerts] == sorted(
        (alert["timestamp"] for alert in alerts), reverse=True
    )


def test_alert_range_is_inclusive_and_newest_first(client):
    base = 1_700_000_000.0
    records = [
        reading(
            sensor_id=f"R{index}",
            name=f"Range sensor {index}",
            value=600.0,
            timestamp=base + index,
        )
        for index in range(5)
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    response = client.get(
        "/api/sensors/history/alerts",
        params={"start": base + 1, "end": base + 3},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 3
    assert [alert["sensor_id"] for alert in response.json()["alerts"]] == [
        "R3",
        "R2",
        "R1",
    ]


def test_recent_alerts_endpoint_uses_recent_path_without_active_alias(client):
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=600.0, timestamp=1_700_000_000.0)],
    )

    recent = client.get("/api/alerts/recent")
    legacy = client.get("/api/alerts/active")

    assert recent.status_code == 200
    assert len(recent.json()) == 1
    assert recent.json()[0]["source"] == "rule"
    assert legacy.status_code == 404

def test_alert_stats_use_all_stored_alerts_not_only_recent_twenty(client):
    records = [
        reading(
            sensor_id=f"STAT{index:02d}",
            name=f"Stats sensor {index}",
            value=600.0,
            timestamp=1_700_000_000.0 + index,
        )
        for index in range(25)
    ]
    client.post("/api/data/upload/json?push_live=false", json=records)

    response = client.get("/api/alerts/stats")

    assert response.status_code == 200
    assert response.json()["total"] == 25
    assert response.json()["by_level"]["red"] == 25
    assert response.json()["by_source"]["rule"] == 25
def test_alert_storage_keeps_only_newest_fifty_thousand(app):
    engine = app.state.services.engine
    for index in range(50_001):
        engine._retain_alert(
            Alert(
                id=uuid.UUID(int=index + 1),
                sensor_id="S01",
                sensor_name="Main span strain",
                level="red",
                message="threshold exceeded",
                value=600.0,
                threshold=600.0,
                source="rule",
                timestamp=float(index),
            )
        )

    recent = engine.get_recent_alerts()

    assert engine.get_alert_count() == 50_000
    assert len(recent) == 20
    assert recent[0]["id"] == str(uuid.UUID(int=50001))
    assert recent[-1]["id"] == str(uuid.UUID(int=49982))
    assert [alert["id"] for alert in engine.get_alerts_range(0.0, 1.0)] == [
        str(uuid.UUID(int=2))
    ]
    assert engine.get_alert_stats()["total"] == 50_000


def test_alert_storage_evicts_the_oldest_alert_time_not_the_oldest_arrival(
    app, client
):
    engine = app.state.services.engine
    base = 1_700_000_000.0
    for index in range(50_000):
        engine._retain_alert(
            Alert(
                id=uuid.UUID(int=index + 1),
                sensor_id="S01",
                sensor_name="Main span strain",
                level="red",
                message="threshold exceeded",
                value=600.0,
                threshold=600.0,
                source="rule",
                timestamp=base + index,
            )
        )

    engine._retain_alert(
        Alert(
            id=uuid.UUID(int=50001),
            sensor_id="S01",
            sensor_name="Main span strain",
            level="red",
            message="threshold exceeded",
            value=600.0,
            threshold=600.0,
            source="rule",
            timestamp=base - 1,
        )
    )

    recent = client.get("/api/alerts/").json()["alerts"]
    backfill = client.get(
        "/api/sensors/history/alerts",
        params={"start": base - 1, "end": base - 1},
    ).json()
    stats = client.get("/api/alerts/stats").json()

    assert stats["total"] == 50_000
    assert backfill["count"] == 0
    assert recent[0]["id"] == str(uuid.UUID(int=50000))
    assert recent[-1]["id"] == str(uuid.UUID(int=49981))


def test_all_sensor_thresholds_are_configurable(client):
    updates = {
        "strain_yellow": 301,
        "strain_orange": 451,
        "strain_red": 601,
        "displacement_yellow": 31,
        "displacement_orange": 51,
        "displacement_red": 81,
        "acceleration_yellow": 2.1,
        "acceleration_orange": 3.6,
        "acceleration_red": 5.1,
        "temperature_yellow": 46,
        "temperature_orange": 56,
        "temperature_red": 66,
    }

    response = client.post("/api/data/config/thresholds", params=updates)
    config = client.get("/api/data/config/thresholds").json()

    assert response.status_code == 200
    assert response.json()["updated"] == {
        key: float(value) for key, value in updates.items()
    }
    assert config == {
        "strain": {"yellow": 301.0, "orange": 451.0, "red": 601.0},
        "displacement": {"yellow": 31.0, "orange": 51.0, "red": 81.0},
        "acceleration": {"yellow": 2.1, "orange": 3.6, "red": 5.1},
        "temperature": {"yellow": 46.0, "orange": 56.0, "red": 66.0},
    }


def test_alert_range_rejects_reversed_bounds(client):
    response = client.get(
        "/api/sensors/history/alerts",
        params={"start": 10, "end": 5},
    )

    assert response.status_code == 400
    assert "start" in str(response.json()).lower()


def test_alert_range_type_errors_are_reported_as_400(client):
    response = client.get(
        "/api/sensors/history/alerts",
        params={"start": "bad", "end": 5},
    )

    assert response.status_code == 400
    assert "detail" in response.json()
def test_cooldown_does_not_suppress_late_readings_outside_ten_seconds(client):
    base = 1_700_000_000.0
    client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=600.0, timestamp=base + 1000)],
    )

    late = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=600.0, timestamp=base)],
    )
    still_cooling_down = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=600.0, timestamp=base + 995)],
    )

    assert late.json()["alerts_triggered"] == 1
    assert still_cooling_down.json()["alerts_triggered"] == 0
    alerts = client.get("/api/alerts/").json()["alerts"]
    assert [alert["timestamp"] for alert in alerts] == [base + 1000, base]
def test_backfilled_readings_use_the_same_cooldown_window(client):
    base = 1_700_000_000.0
    for timestamp in (base + 1000, base, base + 5):
        client.post(
            "/api/data/upload/json?push_live=false",
            json=[reading(value=600.0, timestamp=timestamp)],
        )

    alerts = client.get("/api/alerts/").json()["alerts"]
    assert [alert["timestamp"] for alert in alerts] == [base + 1000, base]


def test_threshold_update_clears_cooldown_for_sensor_type(client):
    base = 1_700_000_000.0
    first = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=600.0, timestamp=base)],
    )
    update = client.post(
        "/api/data/config/thresholds",
        params={"strain_red": 601},
    )
    after_update = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(value=601.0, timestamp=base + 5)],
    )

    alerts = client.get("/api/alerts/").json()["alerts"]

    assert first.json()["alerts_triggered"] == 1
    assert update.status_code == 200
    assert after_update.json()["alerts_triggered"] == 1
    assert [alert["threshold"] for alert in alerts] == [601.0, 600.0]


@pytest.mark.parametrize(
    "updates",
    [
        {"temperature_red": float("nan")},
        {"temperature_yellow": -1},
        {"temperature_yellow": 10, "temperature_orange": 15, "temperature_red": 5},
        {"temperature_yellow": 45, "temperature_orange": 45, "temperature_red": 65},
    ],
)
def test_invalid_threshold_updates_are_rejected_without_partial_changes(
    client, updates
):
    before = client.get("/api/data/config/thresholds").json()

    response = client.post("/api/data/config/thresholds", params=updates)

    assert response.status_code == 400
    assert client.get("/api/data/config/thresholds").json() == before


def test_negative_threshold_alert_message_reports_absolute_value(client):
    response = client.post(
        "/api/data/upload/json?push_live=false",
        json=[
            reading(
                sensor_id="NEG-01",
                name="Negative strain",
                value=-600.0,
                timestamp=1_700_000_000.0,
            )
        ],
    )

    assert response.json()["alerts_triggered"] == 1
    alert = client.get("/api/alerts/").json()["alerts"][0]
    assert alert["value"] == -600.0
    assert "-600.00 >=" not in alert["message"]
    assert "600.00 >= 600" in alert["message"]
