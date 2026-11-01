"""Threshold provenance, units, and provisional/authoritative boundaries."""

from __future__ import annotations

import json

import pytest
from app.config import AppConfig
from app.threshold_provenance import THRESHOLD_UNITS, ThresholdProvenance


def test_defaults_are_explicitly_provisional_and_not_authoritative() -> None:
    config = AppConfig()
    provenance = config.threshold_provenance

    assert provenance.status == "provisional"
    assert provenance.authoritative is False
    assert provenance.profile_version == "provisional-default-v1"
    assert provenance.source_document is None
    assert provenance.effective_date is None
    assert "not an authoritative" in provenance.notes
    assert dict(provenance.units) == THRESHOLD_UNITS


def test_threshold_profile_endpoint_and_health_expose_provenance(client) -> None:
    profile = client.get("/api/data/config/threshold-profile")
    health = client.get("/api/health")

    assert profile.status_code == 200
    payload = profile.json()
    assert payload["provenance"]["status"] == "provisional"
    assert payload["provenance"]["authoritative"] is False
    assert payload["provenance"]["units"]["strain"] == "microstrain (µε)"
    assert payload["thresholds"]["strain"]["yellow"] == 300.0

    assert health.status_code == 200
    assert health.json()["threshold_profile"]["status"] == "provisional"
    assert health.json()["threshold_profile"]["profile_version"] == (
        "provisional-default-v1"
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
        "units": dict(THRESHOLD_UNITS),
    }
    value.update(overrides)

    with pytest.raises(ValueError):
        ThresholdProvenance.from_dict(value)


def test_invalid_provenance_environment_json_is_rejected() -> None:
    with pytest.raises(ValueError):
        AppConfig.from_env({"BRIDGE_THRESHOLD_PROVENANCE_JSON": "not-json"})


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
