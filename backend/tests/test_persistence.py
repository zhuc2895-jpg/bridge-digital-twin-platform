"""Checkpoint persistence and restart recovery coverage."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

import pytest
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.dependencies import create_services
from app.engine.data_engine import MonitoringEngine
from app.main import create_app
from app.persistence import (
    CheckpointError,
    CheckpointManager,
    JsonCheckpointStore,
)
from app.sensor_batch import LiveEligibility, SensorBatch
from app.sensor_reading import SensorReadingRecord
from app.threshold_provenance import (
    THRESHOLD_UNITS,
    ThresholdProvenance,
    default_threshold_profile_document,
)

from tests.factories import reading
from tests.helpers import ingest_records


class MemoryCheckpointStore:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None
        self.load_count = 0
        self.save_count = 0

    def load(self) -> dict[str, Any] | None:
        self.load_count += 1
        return copy.deepcopy(self.payload)

    def save(self, payload: Mapping[str, Any]) -> None:
        self.save_count += 1
        self.payload = copy.deepcopy(dict(payload))


def _records(count: int, *, start: float = 1000.0) -> list[SensorReadingRecord]:
    return [
        reading(
            sensor_id="S01",
            value=100.0 + index,
            timestamp=start + index,
        )
        for index in range(count)
    ]


def _process(
    services,
    records: list[SensorReadingRecord],
    *,
    live: bool = False,
) -> None:
    services.processor.process(
        SensorBatch(
            records=records,
            live_eligibility=(
                LiveEligibility.EXTERNAL if live else LiveEligibility.BACKFILL
            ),
        )
    )


def _persistent_services(path: Path):
    services = create_services(checkpoint_path=path)
    services.live_stream_autostart = False
    return services


def test_empty_checkpoint_starts_clean_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "monitoring.json"
    services = _persistent_services(path)

    assert services.persistence is not None
    assert services.persistence.restored is False
    assert path.exists() is False
    assert services.engine.get_sensor_count() == 0
    assert services.engine.get_time_range() == {
        "start": None,
        "end": None,
        "has_data": False,
    }


def test_first_write_persists_and_restores_queries_alerts_and_thresholds(
    tmp_path: Path,
) -> None:
    path = tmp_path / "monitoring.json"
    services = _persistent_services(path)
    records = _records(3)
    records[-1]["value"] = 1000.0

    with TestClient(create_app(services)) as client:
        response = client.post(
            "/api/data/upload/json",
            params={"push_live": "false"},
            json=records,
        )
        assert response.status_code == 200
        assert path.exists()
        threshold_response = client.post(
            "/api/data/config/thresholds",
            params={"strain_yellow": 250.0},
        )
        assert threshold_response.status_code == 200
        before_latest = client.get("/api/sensors/S01").json()
        before_range = client.get("/api/sensors/history/timerange").json()
        before_snapshot = client.get(
            "/api/sensors/history/snapshot",
            params={"ts": 1002.0},
        ).json()
        before_alerts = client.get(
            "/api/sensors/history/alerts",
            params={"start": 900.0, "end": 1100.0},
        ).json()

    restarted = _persistent_services(path)
    assert restarted.persistence is not None
    assert restarted.persistence.restored is True
    assert restarted.engine.get_latest("S01") == before_latest
    assert restarted.engine.get_time_range() == before_range
    assert restarted.engine.get_snapshot_at(1002.0) == before_snapshot
    assert restarted.engine.get_alerts_range(900.0, 1100.0) == before_alerts["alerts"]
    assert restarted.engine.thresholds["strain"]["yellow"] == 250.0

    with TestClient(create_app(restarted)) as client:
        health = client.get("/api/health").json()
        assert health["sensor_count"] == 1
        assert health["persistence"]["restored"] is True
        assert client.get("/api/sensors/S01").json() == before_latest


def test_abnormal_exit_keeps_last_committed_batch(tmp_path: Path) -> None:
    path = tmp_path / "monitoring.json"
    services = _persistent_services(path)
    records = _records(4)
    records[-1]["value"] = 1000.0

    _process(services, records)

    assert path.exists()
    restarted = _persistent_services(path)
    assert restarted.persistence is not None
    assert restarted.persistence.restored is True
    assert restarted.engine.get_latest("S01") == services.engine.get_latest("S01")
    assert len(restarted.engine.get_alerts_range(0.0, 2000.0)) == 1
    assert restarted.engine.get_snapshot_at(1003.0) == {
        "S01": {
            "sensor_id": "S01",
            "name": "Main span strain",
            "type": "strain",
            "value": 1000.0,
            "timestamp": 1003.0,
            "physical_state": "yellow",
            "connection_state": "online",
        }
    }


def test_restart_restores_threshold_provenance_with_its_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "monitoring.json"
    provenance = ThresholdProvenance.from_dict(
        {
            "status": "authoritative",
            "profile_version": "bridge-srs-2026.1",
            "source_document": "Bridge Structural Monitoring SRS",
            "source_version": "2026.1",
            "source_section": "5.3 Threshold table",
            "effective_date": "2026-12-01",
            "approved_by": "Chief Bridge Engineer",
            "scope": "S01-S08",
            "units": dict(THRESHOLD_UNITS),
        }
    )
    thresholds = {
        sensor_type: dict(levels)
        for sensor_type, levels in default_threshold_profile_document().thresholds.items()
    }
    thresholds["strain"]["yellow"] = 310.0
    services = create_services(
        checkpoint_path=path,
        config=AppConfig(
            thresholds=thresholds,
            sensor_thresholds={},
            threshold_provenance=provenance,
        ),
    )
    services.live_stream_autostart = False
    _process(services, _records(1))

    restarted = _persistent_services(path)
    assert restarted.engine.thresholds["strain"]["yellow"] == 310.0
    assert restarted.engine.threshold_provenance == provenance
    with TestClient(create_app(restarted)) as client:
        profile = client.get("/api/data/config/threshold-profile").json()
        health = client.get("/api/health").json()

    assert profile["provenance"]["profile_version"] == "bridge-srs-2026.1"
    assert health["threshold_profile"]["profile_version"] == "bridge-srs-2026.1"


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version": 1, "state": {',
        b'{"schema_version": 999, "state": {}}',
        b'{"schema_version": 1}',
        b'{"schema_version": 1, "state": {"thresholds": "broken"}}',
    ],
)
def test_damaged_or_incomplete_checkpoint_does_not_block_startup(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    payload: bytes,
) -> None:
    path = tmp_path / "monitoring.json"
    path.write_bytes(payload)

    with caplog.at_level("WARNING", logger="app.persistence"):
        services = _persistent_services(path)

    assert services.persistence is not None
    assert services.persistence.restored is False
    assert services.persistence.last_error is not None
    assert services.engine.get_sensor_count() == 0
    assert "Ignoring" in caplog.text
    with TestClient(create_app(services)) as client:
        assert client.get("/api/health").status_code == 200


def test_engine_round_trip_rebuilds_rolling_window_and_full_history() -> None:
    engine = MonitoringEngine(window_size=500)
    ingest_records(engine, _records(510))
    engine.submit_alert(
        sensor_id="S01",
        sensor_name="Main span strain",
        level="yellow",
        message="test alert",
        value=600.0,
        threshold=300.0,
        source="rule",
        timestamp=1500.0,
    )

    restored = MonitoringEngine(window_size=500)
    restored.restore_state(engine.export_state())

    assert restored.get_time_range() == engine.get_time_range()
    assert len(restored._history["S01"]) == 500
    assert restored._history["S01"][0].timestamp == 1010.0
    assert len(restored._full_history["S01"]) == 510
    assert len(restored._reading_timestamps["S01"]) == 510
    assert restored.get_snapshot_at(1200.0) == engine.get_snapshot_at(1200.0)
    assert restored.get_alerts_range(0.0, 2000.0) == engine.get_alerts_range(0.0, 2000.0)
    assert restored.get_alert_stats() == engine.get_alert_stats()


def test_restored_cooldown_and_detection_sequence_continue() -> None:
    engine = MonitoringEngine()
    first = engine.submit_alert(
        sensor_id="S01",
        sensor_name="Main span strain",
        level="yellow",
        message="first",
        value=310.0,
        threshold=300.0,
        source="rule",
        timestamp=1000.0,
    )
    assert first is not None

    restored = MonitoringEngine()
    restored.restore_state(engine.export_state())

    assert (
        restored.submit_alert(
            sensor_id="S01",
            sensor_name="Main span strain",
            level="yellow",
            message="inside cooldown",
            value=311.0,
            threshold=300.0,
            source="rule",
            timestamp=1009.999,
        )
        is None
    )
    second = restored.submit_alert(
        sensor_id="S01",
        sensor_name="Main span strain",
        level="yellow",
        message="after cooldown",
        value=312.0,
        threshold=300.0,
        source="rule",
        timestamp=1010.0,
    )
    assert second is not None
    assert second.detection_sequence == first.detection_sequence + 1


def test_replaceable_store_adapter_works_without_engine_changes() -> None:
    store = MemoryCheckpointStore()
    services = create_services(checkpoint_store=store)
    _process(services, _records(2))

    assert store.save_count == 1
    assert store.payload is not None

    restarted = create_services(checkpoint_store=store)
    assert restarted.persistence is not None
    assert restarted.persistence.restored is True
    assert restarted.engine.get_latest("S01") == services.engine.get_latest("S01")


def test_failed_atomic_replace_keeps_previous_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "monitoring.json"
    engine = MonitoringEngine()
    ingest_records(engine, _records(1))
    manager = CheckpointManager(engine, JsonCheckpointStore(path))
    assert manager.commit() is True
    previous = path.read_bytes()

    def fail_replace(source, destination) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr("app.persistence.os.replace", fail_replace)
    ingest_records(engine, _records(1, start=2000.0))
    assert manager.commit() is False
    assert manager.last_error is not None
    assert path.read_bytes() == previous
    assert list(tmp_path.glob(".*.tmp")) == []


def test_checkpoint_store_rejects_invalid_payloads(tmp_path: Path) -> None:
    path = tmp_path / "monitoring.json"
    store = JsonCheckpointStore(path)
    assert store.load() is None
    path.write_text("", encoding="utf-8")
    with pytest.raises(CheckpointError):
        store.load()
