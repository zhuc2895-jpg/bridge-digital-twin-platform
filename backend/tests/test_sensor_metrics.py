from __future__ import annotations

import time

from app.engine.data_engine import MonitoringEngine
from app.live_stream import capture_live_snapshot
from app.sensor_batch import LiveEligibility, SensorBatch
from app.sensor_metrics import ONLINE_SENSOR_FRESHNESS_SECONDS

from tests.factories import reading


def _ingest(
    engine: MonitoringEngine,
    records: list[dict],
    eligibility: LiveEligibility = LiveEligibility.INTERNAL,
) -> None:
    engine.ingest(SensorBatch(records=records, live_eligibility=eligibility))


def test_online_sensor_freshness_is_sixty_seconds():
    assert ONLINE_SENSOR_FRESHNESS_SECONDS == 60.0


def test_online_sensor_count_uses_inclusive_past_and_future_boundaries():
    engine = MonitoringEngine()
    reference = 1_000_000.0
    _ingest(
        engine,
        [
            reading(sensor_id="PAST-EDGE", timestamp=reference - 60.0),
            reading(sensor_id="STALE", timestamp=reference - 60.001),
            reading(sensor_id="FUTURE-EDGE", timestamp=reference + 60.0),
            reading(sensor_id="TOO-FUTURE", timestamp=reference + 60.001),
        ],
    )

    stats = engine.get_stats(reference_time=reference)

    assert stats["sensor_count"] == 4
    assert stats["online_sensor_count"] == 2
    assert engine.get_online_sensor_count(reference) == 2


def test_time_invalid_latest_reading_is_offline_and_physical_state_falls_back():
    engine = MonitoringEngine()
    reference = 1_000_000.0
    _ingest(
        engine,
        [reading(sensor_id="S01", value=100.0, timestamp=reference - 20.0)],
    )
    _ingest(
        engine,
        [reading(sensor_id="S01", value=600.0, timestamp=reference + 61.0)],
    )

    valid_latest = engine.get_latest_time_valid(reference)

    assert engine.get_latest("S01")["value"] == 600.0
    assert valid_latest["S01"]["value"] == 100.0
    assert engine.get_online_sensor_count(reference) == 0


def test_sensor_without_time_valid_reading_has_no_physical_state_source():
    engine = MonitoringEngine()
    reference = 1_000_000.0
    _ingest(
        engine,
        [reading(sensor_id="FUTURE", value=600.0, timestamp=reference + 61.0)],
    )

    assert engine.get_latest_time_valid(reference) == {}
    assert engine.get_online_sensor_count(reference) == 0


def test_time_valid_fallback_survives_full_history_eviction():
    engine = MonitoringEngine()
    engine._max_full_history = 1
    reference = time.time()
    _ingest(
        engine,
        [reading(sensor_id="S01", value=100.0, timestamp=reference - 20.0)],
    )
    _ingest(
        engine,
        [reading(sensor_id="S01", value=600.0, timestamp=reference + 61.0)],
    )

    valid_latest = engine.get_latest_time_valid(reference)

    assert len(engine._full_history["S01"]) == 1
    assert valid_latest["S01"]["value"] == 100.0


def test_future_reading_becomes_time_valid_as_reference_advances():
    engine = MonitoringEngine()
    reference = time.time()
    _ingest(
        engine,
        [reading(sensor_id="S01", value=600.0, timestamp=reference + 61.0)],
    )

    assert engine.get_latest_time_valid(reference) == {}
    assert engine.get_latest_time_valid(reference + 1.0)["S01"]["value"] == 600.0


def test_period_reading_count_includes_all_paths_and_inclusive_bounds():
    engine = MonitoringEngine()
    base = 1_000_000.0
    _ingest(
        engine,
        [reading(sensor_id="S01", timestamp=base)],
        LiveEligibility.INTERNAL,
    )
    _ingest(
        engine,
        [reading(sensor_id="S02", timestamp=base + 1.0)],
        LiveEligibility.BACKFILL,
    )
    _ingest(
        engine,
        [reading(sensor_id="S03", timestamp=base + 2.0)],
        LiveEligibility.EXTERNAL,
    )
    _ingest(
        engine,
        [
            reading(sensor_id="S04", timestamp=base - 0.001),
            reading(sensor_id="S05", timestamp=base + 2.001),
        ],
    )

    assert engine.get_period_reading_count(base, base + 2.0) == 3


def test_period_reading_count_survives_full_history_eviction_and_out_of_order_data():
    engine = MonitoringEngine()
    engine._max_full_history = 2
    base = 1_000_000.0
    _ingest(
        engine,
        [
            reading(sensor_id="S01", timestamp=base + 2.0),
            reading(sensor_id="S01", timestamp=base),
            reading(sensor_id="S01", timestamp=base + 1.0),
            reading(sensor_id="S01", timestamp=base + 3.0),
            reading(sensor_id="S01", timestamp=base + 4.0),
        ],
    )

    assert len(engine._full_history["S01"]) == 2
    assert engine.get_period_reading_count(base, base + 4.0) == 5


def test_cumulative_reading_count_resets_with_a_new_process_engine():
    first_engine = MonitoringEngine()
    _ingest(
        first_engine,
        [reading(sensor_id=f"S{index:02d}") for index in range(5)],
        LiveEligibility.BACKFILL,
    )

    assert first_engine.get_stats()["total_readings"] == 5
    assert MonitoringEngine().get_stats()["total_readings"] == 0


def test_live_frame_and_health_share_the_same_online_sensor_count(client, app):
    now = time.time()
    services = app.state.services
    _ingest(
        services.engine,
        [
            reading(sensor_id="ONLINE", timestamp=now - 10.0),
            reading(sensor_id="STALE", timestamp=now - 120.0),
            reading(sensor_id="FUTURE-INVALID", timestamp=now + 61.0),
        ],
    )

    health = client.get("/api/health").json()
    snapshot = capture_live_snapshot(
        services.engine,
        services.processing_lock,
    )

    assert health["sensor_count"] == 3
    assert health["online_sensor_count"] == 1
    assert snapshot.stats["sensor_count"] == 3
    assert snapshot.stats["online_sensor_count"] == 1


def test_counts_include_api_uploads_injection_and_simulator_paths(client, app):
    services = app.state.services
    now = time.time()
    backfill = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(sensor_id="BACKFILL", timestamp=now - 1.0)],
    )
    live_upload = client.post(
        "/api/data/upload/json?push_live=true",
        json=[reading(sensor_id="LIVE-UPLOAD", timestamp=now - 1.0)],
    )
    injection = client.post(
        "/api/analysis/inject-anomaly",
        json={"sensor_id": "S01"},
    )
    simulator_records = services.simulator.next_readings(timestamp=now)
    services.processor.process(
        SensorBatch(
            records=simulator_records,
            live_eligibility=LiveEligibility.INTERNAL,
        )
    )

    assert backfill.status_code == 200
    assert live_upload.status_code == 200
    assert injection.status_code == 200
    stats = services.engine.get_stats(reference_time=now)
    assert stats["total_readings"] == 11
    assert services.engine.get_period_reading_count(now - 60.0, now + 60.0) == 11
