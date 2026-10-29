import json
from pathlib import Path

MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "vba" / "manifest.json"
)


def test_vba_benchmark_manifest_defines_the_acceptance_contract():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["repository_path"] == "benchmarks/vba"
    assert manifest["normalized_csv"]["path"] == "benchmarks/vba/normalized.csv"
    assert manifest["normalized_csv"]["sha256"] == (
        "15857EB70FFF4F075CA73B1D58F5541882A2BF18F5208A206F76E576F8942E8F"
    )
    assert manifest["source"]["sha256"] == (
        "001F8A1ADD06649A6156FA7D33440D889A9E0CB036C17895E9F357BD1E281DA5"
    )
    assert manifest["corpus"]["recording_count"] == 68
    assert manifest["corpus"]["case_counts"] == {
        "INT": 26,
        "RCV": 10,
        "DMG1": 12,
        "DMG2": 10,
        "DMG3": 10,
    }
    assert manifest["corpus"]["ignored_columns"] == [10, 11, 12]
    assert manifest["conversion"]["aggregation"] == "rms"
    assert manifest["conversion"]["partial_bucket_policy"] == "discard"
    assert manifest["evaluation"]["primary_unit"] == "recording"
    assert manifest["evaluation"]["fold_count"] == 5
    assert manifest["evaluation"]["random_seed"] == 42
    assert manifest["evaluation"]["baseline_cases"] == ["INT"]
    assert manifest["metrics"] == [
        "accuracy",
        "false_positive_rate",
        "recall",
        "precision",
        "f1",
        "confusion_matrix",
        "per_case",
        "per_fold",
        "per_sensor_alert_counts",
        "alert_source_counts",
        "alert_level_counts",
    ]
    assert manifest["acceptance"] == {
        "accuracy_min": 0.9,
        "false_positive_rate_max": 0.1,
        "require_all_components": True,
        "require_all_baselines_ready": True,
    }
