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
