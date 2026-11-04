import time
from typing import cast

import pytest
from app.engine.data_engine import MonitoringEngine
from app.history_read import (
    HistoryReadModel,
    HistoryTimestampOutOfRangeError,
    HistoryUnavailableError,
)
from app.sensor_batch import SensorBatch
from app.sensor_reading import SensorReadingRecord

from tests.factories import reading
from tests.helpers import TrackingLock


def _engine_with_readings() -> MonitoringEngine:
    engine = MonitoringEngine()
    now = time.time()
    engine.ingest(
        SensorBatch(
            records=cast(
                list[SensorReadingRecord],
                [
                    reading(sensor_id="S01", value=100.0, timestamp=now - 20),
                    reading(sensor_id="S01", value=200.0, timestamp=now - 10),
                    reading(sensor_id="S02", value=300.0, timestamp=now - 5),
                ],
            )
        )
    )
    return engine


def test_report_snapshot_uses_one_shared_read_boundary() -> None:
    engine = _engine_with_readings()
    lock = TrackingLock()
    history = HistoryReadModel(engine, lock)

    snapshot = history.report_snapshot(time.time() - 60, time.time())

    assert lock.acquisitions == 1
    assert snapshot.latest["S01"]["value"] == 200.0
    assert snapshot.period_reading_count == 3


def test_latest_retained_snapshot_uses_history_end() -> None:
    engine = _engine_with_readings()
    history = HistoryReadModel(engine, TrackingLock())

    timestamp, snapshot = history.latest_retained_snapshot()

    assert timestamp == engine.get_time_range()["end"]
    assert snapshot["S01"]["value"] == 200.0
    assert snapshot["S02"]["value"] == 300.0


def test_retained_snapshot_rejects_timestamp_outside_history() -> None:
    engine = _engine_with_readings()
    history = HistoryReadModel(engine, TrackingLock())

    with pytest.raises(HistoryTimestampOutOfRangeError):
        history.snapshot_at_retained_time(engine.get_time_range()["start"] - 1)


def test_empty_history_is_reported_from_the_read_seam() -> None:
    history = HistoryReadModel(MonitoringEngine(), TrackingLock())

    with pytest.raises(HistoryUnavailableError):
        history.latest_retained_snapshot()
