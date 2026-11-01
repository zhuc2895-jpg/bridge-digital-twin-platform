"""Threshold provenance, units, and provisional/authoritative boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.config import AppConfig
from app.dependencies import create_services
from app.engine.data_engine import MonitoringEngine
from app.main import create_app
from app.sensor_batch import SensorBatch
from app.threshold_provenance import THRESHOLD_UNITS, ThresholdProvenance
from app.threshold_provenance import (
    ThresholdProfileDocument,
    default_threshold_profile_document,
)
from fastapi.testclient import TestClient


def test_defaults_are_the_code_derived_design_basis_profile() -> None:
    config = AppConfig()
    provenance = config.threshold_provenance

    assert provenance.status == "provisional"
    assert provenance.authoritative is False
    assert provenance.profile_version == "competition-design-basis-v1"
    assert "JT/T 1037-2022" in str(provenance.source_document)
    assert provenance.effective_date is None
    assert provenance.approved_by is None
    assert config.sensor_thresholds["S01"]["yellow"] == 960.0
    assert config.sensor_thresholds["S08"]["red"] == 60.0
    assert config.thresholds["strain"]["orange"] == 1200.0
    assert dict(provenance.units) == THRESHOLD_UNITS


def test_threshold_profile_endpoint_and_health_expose_provenance() -> None:
    config = AppConfig()
    services = create_services(config=config)
    services.live_stream_autostart = False
    application = create_app(services, config=config)
    with TestClient(application) as client:
        profile = client.get("/api/data/config/threshold-profile")
        health = client.get("/api/health")

    assert profile.status_code == 200
    payload = profile.json()
    assert payload["provenance"]["status"] == "provisional"
    assert payload["provenance"]["authoritative"] is False
    assert payload["provenance"]["units"]["strain"] == "microstrain (µε)"
    assert payload["thresholds"]["strain"]["yellow"] == 960.0
    assert payload["sensor_thresholds"]["S01"]["yellow"] == 960.0

    assert health.status_code == 200
    assert health.json()["threshold_profile"]["status"] == "provisional"
    assert health.json()["threshold_profile"]["profile_version"] == (
        "competition-design-basis-v1"
    )


def test_authoritative_provenance_is_accepted_with_complete_metadata() -> None:
    provenance = {
        "status": "authoritative",
        "profile_version": "bridge-srs-2026.1",
        "source_document": "Bridge Structural Monitoring SRS",
        "source_version": "2026.1",
        "source_section": "5.3 Threshold table",
        "effective_date": "2026-12-01",
        "approved_by": "Chief Bridge Engineer",
        "scope": "all sensors of the same type",
        "units": dict(THRESHOLD_UNITS),
        "notes": "Approved engineering table.",
    }
    config = AppConfig.from_env(
        {"BRIDGE_THRESHOLD_PROVENANCE_JSON": json.dumps(provenance)}
    )

    assert config.threshold_provenance.authoritative is True
    assert config.threshold_provenance.profile_version == "bridge-srs-2026.1"
    assert config.threshold_provenance.source_section == "5.3 Threshold table"
    assert config.threshold_provenance.approved_by == "Chief Bridge Engineer"


@pytest.mark.parametrize(
    "overrides",
    [
        {"approved_by": None},
        {"source_section": None},
        {"effective_date": "2026/12/01"},
        {"status": "approved"},
        {"units": {"strain": "ue"}},
        {"scope": None},
        {"scope": ""},
    ],
)
def test_authoritative_provenance_rejects_incomplete_or_invalid_metadata(
    overrides,
) -> None:
    value = {
        "status": "authoritative",
        "profile_version": "bridge-srs-2026.1",
        "source_document": "Bridge Structural Monitoring SRS",
        "source_version": "2026.1",
        "source_section": "5.3 Threshold table",
        "effective_date": "2026-12-01",
        "approved_by": "Chief Bridge Engineer",
        "scope": "all strain and displacement sensors",
        "units": dict(THRESHOLD_UNITS),
    }
    value.update(overrides)

    with pytest.raises(ValueError):
        ThresholdProvenance.from_dict(value)


def test_invalid_provenance_environment_json_is_rejected() -> None:
    with pytest.raises(ValueError):
        AppConfig.from_env({"BRIDGE_THRESHOLD_PROVENANCE_JSON": "not-json"})


def test_type_level_environment_override_disables_default_sensor_overrides() -> None:
    config = AppConfig.from_env({"BRIDGE_STRAIN_YELLOW": "1000"})

    assert config.thresholds["strain"]["yellow"] == 1000.0
    assert config.sensor_thresholds == {}
    assert config.threshold_provenance.profile_version == "provisional-default-v1"


def test_authoritative_profile_document_replaces_values_and_provenance(
    tmp_path,
) -> None:
    profile_path = tmp_path / "authoritative-thresholds.json"
    profile_path.write_text(
        json.dumps(
            {
                "thresholds": {
                    "strain": {"yellow": 310, "orange": 470, "red": 640},
                    "displacement": {"yellow": 31, "orange": 51, "red": 81},
                    "acceleration": {"yellow": 2.1, "orange": 3.6, "red": 5.1},
                    "temperature": {"yellow": 46, "orange": 56, "red": 66},
                },
                "provenance": {
                    "status": "authoritative",
                    "profile_version": "bridge-srs-2026.1",
                    "source_document": "Bridge Structural Monitoring SRS",
                    "source_version": "2026.1",
                    "source_section": "5.3 Threshold table",
                    "effective_date": "2026-12-01",
                    "approved_by": "Chief Bridge Engineer",
                    "scope": "S01-S08",
                    "units": dict(THRESHOLD_UNITS),
                },
            }
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env(
        {"BRIDGE_THRESHOLD_PROFILE_PATH": str(profile_path)}
    )

    assert config.thresholds["strain"] == {
        "yellow": 310.0,
        "orange": 470.0,
        "red": 640.0,
    }
    assert config.thresholds["acceleration"]["red"] == 5.1
    assert config.threshold_provenance.authoritative is True
    assert config.threshold_provenance.profile_version == "bridge-srs-2026.1"


def test_threshold_profile_document_rejects_individual_value_overrides(
    tmp_path,
) -> None:
    profile_path = tmp_path / "authoritative-thresholds.json"
    profile_path.write_text(
        json.dumps(
            {
                "thresholds": {
                    "strain": {"yellow": 310, "orange": 470, "red": 640},
                    "displacement": {"yellow": 31, "orange": 51, "red": 81},
                    "acceleration": {"yellow": 2.1, "orange": 3.6, "red": 5.1},
                    "temperature": {"yellow": 46, "orange": 56, "red": 66},
                },
                "provenance": {
                    "status": "authoritative",
                    "profile_version": "bridge-srs-2026.1",
                    "source_document": "Bridge Structural Monitoring SRS",
                    "source_version": "2026.1",
                    "source_section": "5.3 Threshold table",
                    "effective_date": "2026-12-01",
                    "approved_by": "Chief Bridge Engineer",
                    "scope": "S01-S08",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="BRIDGE_THRESHOLD_PROFILE_PATH"):
        AppConfig.from_env(
            {
                "BRIDGE_THRESHOLD_PROFILE_PATH": str(profile_path),
                "BRIDGE_STRAIN_YELLOW": "999",
            }
        )


def test_threshold_profile_document_rejects_separate_provenance_json(
    tmp_path,
) -> None:
    profile_path = tmp_path / "authoritative-thresholds.json"
    profile_path.write_text(
        json.dumps(
            {
                "thresholds": {
                    "strain": {"yellow": 310, "orange": 470, "red": 640},
                    "displacement": {"yellow": 31, "orange": 51, "red": 81},
                    "acceleration": {"yellow": 2.1, "orange": 3.6, "red": 5.1},
                    "temperature": {"yellow": 46, "orange": 56, "red": 66},
                },
                "provenance": {
                    "status": "authoritative",
                    "profile_version": "bridge-srs-2026.1",
                    "source_document": "Bridge Structural Monitoring SRS",
                    "source_version": "2026.1",
                    "source_section": "5.3 Threshold table",
                    "effective_date": "2026-12-01",
                    "approved_by": "Chief Bridge Engineer",
                    "scope": "S01-S08",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="BRIDGE_THRESHOLD_PROVENANCE_JSON"):
        AppConfig.from_env(
            {
                "BRIDGE_THRESHOLD_PROFILE_PATH": str(profile_path),
                "BRIDGE_THRESHOLD_PROVENANCE_JSON": "{}",
            }
        )


def test_threshold_profile_document_supports_sensor_specific_overrides(
    tmp_path,
) -> None:
    profile_path = tmp_path / "authoritative-thresholds.json"
    profile_path.write_text(
        json.dumps(
            {
                "thresholds": {
                    "strain": {"yellow": 310, "orange": 470, "red": 640},
                    "displacement": {"yellow": 31, "orange": 51, "red": 81},
                    "acceleration": {"yellow": 2.1, "orange": 3.6, "red": 5.1},
                    "temperature": {"yellow": 46, "orange": 56, "red": 66},
                },
                "sensor_thresholds": {
                    "S04": {"yellow": 1.0, "orange": 2.0, "red": 3.0},
                    "S05": {"yellow": 160.0, "orange": 200.0, "red": 240.0},
                },
                "provenance": {
                    "status": "authoritative",
                    "profile_version": "bridge-srs-2026.1",
                    "source_document": "Bridge Structural Monitoring SRS",
                    "source_version": "2026.1",
                    "source_section": "5.3 Threshold table",
                    "effective_date": "2026-12-01",
                    "approved_by": "Chief Bridge Engineer",
                    "scope": "S01-S08",
                },
            }
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env(
        {"BRIDGE_THRESHOLD_PROFILE_PATH": str(profile_path)}
    )

    assert config.sensor_thresholds["S04"] == {
        "yellow": 1.0,
        "orange": 2.0,
        "red": 3.0,
    }
    assert config.sensor_thresholds["S05"]["red"] == 240.0


def test_engine_prefers_sensor_specific_thresholds_over_type_profile() -> None:
    engine = MonitoringEngine(
        sensor_thresholds={
            "S04": {"yellow": 10.0, "orange": 20.0, "red": 30.0}
        }
    )
    batch = SensorBatch(
        records=[
            {
                "sensor_id": "S04",
                "name": "Cable acceleration",
                "type": "acceleration",
                "value": 15.0,
                "timestamp": 1_700_000_000.0,
            },
            {
                "sensor_id": "S07",
                "name": "Other cable acceleration",
                "type": "acceleration",
                "value": 0.5,
                "timestamp": 1_700_000_000.0,
            },
        ]
    )

    alerts = engine.check_thresholds(batch)

    assert [(alert.sensor_id, alert.level) for alert in alerts] == [("S04", "yellow")]


def test_sensor_specific_thresholds_do_not_apply_to_a_different_sensor_type() -> None:
    engine = MonitoringEngine(
        sensor_thresholds={
            "S01": {"yellow": 960.0, "orange": 1200.0, "red": 1440.0}
        }
    )
    batch = SensorBatch(
        records=[
            {
                "sensor_id": "S01",
                "name": "Mislabeled acceleration channel",
                "type": "acceleration",
                "value": 1.0,
                "timestamp": 1_700_000_000.0,
            }
        ]
    )

    alerts = engine.check_thresholds(batch)

    assert [(alert.sensor_id, alert.level) for alert in alerts] == [("S01", "red")]


def test_engine_round_trip_preserves_sensor_specific_thresholds() -> None:
    engine = MonitoringEngine(
        sensor_thresholds={
            "S04": {"yellow": 10.0, "orange": 20.0, "red": 30.0}
        }
    )
    restored = MonitoringEngine()

    restored.restore_state(engine.export_state())

    assert restored.sensor_thresholds == engine.sensor_thresholds
    assert restored.sensor_threshold_types == engine.sensor_threshold_types
    assert restored.thresholds_for("S04", "acceleration")["red"] == 30.0


def test_engine_round_trip_preserves_threshold_provenance() -> None:
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
    engine = MonitoringEngine(
        thresholds=default_threshold_profile_document().thresholds,
        sensor_thresholds={},
        threshold_provenance=provenance,
    )
    restored = MonitoringEngine()

    restored.restore_state(engine.export_state())

    assert restored.threshold_provenance == provenance


def test_sensor_thresholds_are_wired_into_services_and_profile_api() -> None:
    overrides = {"S04": {"yellow": 10.0, "orange": 20.0, "red": 30.0}}
    config = AppConfig(sensor_thresholds=overrides)
    services = create_services(config=config)
    services.live_stream_autostart = False
    application = create_app(services, config=config)

    assert services.engine.sensor_thresholds == overrides
    with TestClient(application) as client:
        profile = client.get("/api/data/config/threshold-profile").json()

    assert profile["sensor_thresholds"] == overrides


def test_runtime_type_threshold_update_disables_sensor_overrides() -> None:
    config = AppConfig()
    services = create_services(config=config)
    services.live_stream_autostart = False
    application = create_app(services, config=config)

    with TestClient(application) as client:
        response = client.post(
            "/api/data/config/thresholds",
            params={"strain_yellow": 1000.0},
        )

    assert response.status_code == 200
    assert services.engine.sensor_thresholds == {}
    assert services.engine.thresholds_for("S01", "strain")["yellow"] == 1000.0
    assert services.engine.threshold_provenance.profile_version == (
        "provisional-default-v1"
    )


def test_versioned_default_profile_file_matches_code_defaults() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "bridge-threshold-profile.json"
    )
    document = ThresholdProfileDocument.load(path)

    assert document.to_dict() == default_threshold_profile_document().to_dict()
