from __future__ import annotations

import time

from app.engine.data_engine import MonitoringEngine
from app.sensor_batch import LiveEligibility, SensorBatch
from app.sensor_state import highest_physical_state

from tests.factories import reading


def _ingest(
    engine: MonitoringEngine,
    records: list[dict],
    *,
    live_eligibility: LiveEligibility = LiveEligibility.INTERNAL,
) -> None:
    engine.ingest(
        SensorBatch(records=records, live_eligibility=live_eligibility)
    )


def test_latest_projection_uses_abs_sensor_override_and_connection_state() -> None:
    engine = MonitoringEngine()
    reference = 1_700_000_000.0
    _ingest(
        engine,
        [reading(sensor_id="S01", value=-1500.0, timestamp=reference)],
    )

    projected = engine.get_latest("S01", reference_time=reference)

    assert projected is not None
    assert projected["physical_state"] == "red"
    assert projected["connection_state"] == "online"
    assert projected["value"] == -1500.0


def test_temperature_projection_uses_the_same_threshold_policy() -> None:
    engine = MonitoringEngine()
    reference = 1_700_000_000.0
    _ingest(
        engine,
        [
            reading(
                sensor_id="S08",
                sensor_type="temperature",
                value=60.0,
                timestamp=reference,
            )
        ],
    )

    projected = engine.get_latest("S08", reference_time=reference)

    assert projected is not None
    assert projected["physical_state"] == "red"


def test_future_reading_is_unknown_and_offline() -> None:
    engine = MonitoringEngine()
    reference = 1_700_000_000.0
    _ingest(
        engine,
        [reading(sensor_id="S01", value=100.0, timestamp=reference + 61.0)],
    )

    projected = engine.get_latest("S01", reference_time=reference)

    assert projected is not None
    assert projected["physical_state"] == "unknown"
    assert projected["connection_state"] == "offline"


def test_override_type_mismatch_is_unknown_not_type_default() -> None:
    engine = MonitoringEngine()
    reference = 1_700_000_000.0
    _ingest(
        engine,
        [
            reading(
                sensor_id="S01",
                sensor_type="acceleration",
                value=1.0,
                timestamp=reference,
            )
        ],
    )

    projected = engine.get_latest("S01", reference_time=reference)

    assert projected is not None
    assert projected["physical_state"] == "unknown"
    assert projected["connection_state"] == "online"


def test_historical_snapshot_connection_state_is_as_of_query_time() -> None:
    engine = MonitoringEngine()
    base = 1_700_000_000.0
    _ingest(
        engine,
        [reading(sensor_id="S01", value=100.0, timestamp=base)],
    )

    online = engine.get_snapshot_at(base + 30.0)["S01"]
    offline = engine.get_snapshot_at(base + 61.0)["S01"]

    assert online["physical_state"] == "normal"
    assert online["connection_state"] == "online"
    assert offline["physical_state"] == "normal"
    assert offline["connection_state"] == "offline"


def test_threshold_change_is_visible_on_the_next_projection() -> None:
    reference = 1_700_000_000.0
    engine = MonitoringEngine(
        thresholds={
            "strain": {"yellow": 1000.0, "orange": 1200.0, "red": 1400.0},
            "displacement": {"yellow": 30.0, "orange": 50.0, "red": 80.0},
            "acceleration": {"yellow": 2.0, "orange": 3.0, "red": 4.0},
            "temperature": {"yellow": 45.0, "orange": 55.0, "red": 65.0},
        },
        sensor_thresholds={},
    )
    _ingest(
        engine,
        [reading(sensor_id="S01", value=250.0, timestamp=reference)],
    )
    before = engine.get_live_snapshot(reference_time=reference)[0]

    engine.update_thresholds(
        {
            "strain": {"yellow": 100.0, "orange": 200.0, "red": 300.0}
        }
    )
    after = engine.get_live_snapshot(reference_time=reference)[0]

    assert before["physical_state"] == "normal"
    assert after["physical_state"] == "orange"


def test_highest_physical_state_ignores_unknown_when_a_known_state_exists() -> None:
    assert highest_physical_state(["unknown", "normal", "yellow"]) == "yellow"
    assert highest_physical_state(["unknown", "unknown"]) == "unknown"
    assert highest_physical_state([]) == "unknown"


def test_rest_sensor_surfaces_carry_server_authored_state(client) -> None:
    timestamp = time.time()
    upload = client.post(
        "/api/data/upload/json",
        json=[
            reading(
                sensor_id="S01",
                value=-600.0,
                timestamp=timestamp,
            )
        ],
    )
    assert upload.status_code == 200

    latest = client.get("/api/sensors/S01").json()
    snapshot = client.get(
        "/api/sensors/history/snapshot",
        params={"ts": timestamp + 1.0},
    ).json()["S01"]

    assert latest["physical_state"] == "red"
    assert latest["connection_state"] == "online"
    assert snapshot["physical_state"] == "red"
    assert snapshot["connection_state"] == "online"
