"""System acceptance helpers, manifest integrity, and validation gates."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.acceptance import (
    VALIDATION_MANIFEST,
    classification_metrics,
    create_gate,
    load_validation_rows,
    run_rule_algorithm_acceptance,
    sha256_file,
    write_artifacts,
)
from benchmarks.stability import process_memory_bytes


def test_validation_manifest_matches_versioned_dataset() -> None:
    manifest = json.loads(VALIDATION_MANIFEST.read_text(encoding="utf-8"))
    dataset = Path(__file__).resolve().parents[2] / manifest["path"]

    assert sha256_file(dataset) == manifest["sha256"]
    rows = load_validation_rows(dataset)
    assert len(rows) == manifest["rows"] == 69_120
    assert len({row["sensor_id"] for row in rows}) == 8
    assert sum(row["damage_label"] for row in rows) == 1_350
    assert len({row["damage_event"] for row in rows if row["damage_event"]}) == 5
    assert manifest["source_kind"] == "synthetic"
    assert manifest["evaluation"]["accuracy_min"] == 0.9
    assert manifest["evaluation"]["false_positive_rate_max"] == 0.1


def test_classification_metrics_cover_confusion_matrix_and_rates() -> None:
    metrics = classification_metrics(
        [True, True, False, False, False, False],
        [True, False, True, False, False, False],
    )

    assert metrics["confusion_matrix"] == {"tp": 1, "tn": 3, "fp": 1, "fn": 1}
    assert metrics["accuracy"] == 4 / 6
    assert metrics["false_positive_rate"] == 1 / 4
    assert metrics["recall"] == 1 / 2
    assert metrics["precision"] == 1 / 2
    assert metrics["f1"] == 1 / 2


def test_gate_comparison_supports_minimum_and_maximum_limits() -> None:
    assert create_gate(
        "minimum",
        51,
        50,
        comparison=">=",
        unit="qps",
    )["passed"]
    assert not create_gate(
        "maximum",
        501,
        500,
        comparison="<=",
        unit="ms",
    )["passed"]


def test_rule_algorithm_acceptance_passes_versioned_gates() -> None:
    result = run_rule_algorithm_acceptance()

    assert all(gate["passed"] for gate in result["gates"])
    assert result["confirmed_metrics"]["accuracy"] >= 0.9
    assert result["confirmed_metrics"]["false_positive_rate"] <= 0.1
    assert result["event_recall"] == 1.0
    assert result["sample_stats"]["readings"] == 69_120
    assert result["sample_stats"]["windows"] == 1_440
    assert result["threshold_profile"]["provenance"]["profile_version"] == (
        "competition-design-basis-v1"
    )
    assert result["threshold_profile"]["sensor_thresholds"]["S04"]["red"] == 4.41


def test_acceptance_artifacts_include_reproduction_and_environment(
    tmp_path: Path,
) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": "2026-11-01T00:00:00+00:00",
        "status": "passed",
        "exit_reason": "all gates passed",
        "reproduction_command": "python -m benchmarks.acceptance",
        "environment": {"git_commit": "abc123", "python": "Python 3.13"},
        "threshold_profile_version": "test",
        "source_identity": {"validation_dataset": "ABC"},
        "gates": [
            {
                "name": "example",
                "value": 1,
                "limit": 0,
                "comparison": ">=",
                "unit": "ratio",
                "passed": True,
            }
        ],
        "algorithm_acceptance": {
            "dataset": {
                "path": "data/validation/bridge_validation_data.csv",
                "source_kind": "synthetic",
            },
            "dataset_sha256": "ABC",
            "confirmed_metrics": {
                "accuracy": 0.99,
                "false_positive_rate": 0.01,
                "recall": 0.95,
            },
            "raw_metrics": {"accuracy": 0.8},
            "event_recall": 1.0,
        },
    }

    json_path, markdown_path = write_artifacts(payload, tmp_path)
    written = json.loads(json_path.read_text(encoding="utf-8"))
    report = markdown_path.read_text(encoding="utf-8")

    assert written["reproduction_command"] == "python -m benchmarks.acceptance"
    assert "python -m benchmarks.acceptance" in report
    assert "Synthetic data validates behavior" in report


def test_stability_memory_probe_returns_positive_working_set() -> None:
    assert process_memory_bytes() > 0
