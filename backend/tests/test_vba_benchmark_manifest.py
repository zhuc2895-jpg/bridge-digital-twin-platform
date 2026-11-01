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
        "BE13A4CAE46E877C6613FABA9ABF164449CFC58EAA73AC86599473EF078FF7A3"
    )
    assert manifest["source"]["sha256"] == (
        "001F8A1ADD06649A6156FA7D33440D889A9E0CB036C17895E9F357BD1E281DA5"
    )
    assert manifest["corpus"]["recording_count"] == 68
    assert manifest["corpus"]["structural_condition_counts"] == {
        "INT": 26,
        "RCV": 10,
        "DMG1": 12,
        "DMG2": 10,
        "DMG3": 10,
    }
    assert manifest["corpus"]["ignored_columns_one_based"] == [10, 11, 12]
    assert manifest["conversion"]["aggregation"] == "rms"
    assert manifest["conversion"]["partial_bucket_policy"] == "discard"
    assert manifest["evaluation"]["primary_unit"] == "recording"
    assert manifest["evaluation"]["splitter"]["n_splits"] == 5
    assert manifest["evaluation"]["splitter"]["random_state"] == 42
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


def test_vba_benchmark_manifest_defines_reproducible_gates_and_snapshot_scope():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["corpus"]["structural_condition_counts"] == {
        "INT": 26,
        "RCV": 10,
        "DMG1": 12,
        "DMG2": 10,
        "DMG3": 10,
    }
    assert manifest["corpus"]["vibration_case_counts"] == {
        "INT 30km": 11,
        "INT 50km": 5,
        "INT 40km": 10,
        "DMG1 40km": 12,
        "DMG2 40km": 10,
        "RCV 40km": 10,
        "DMG3 40km": 10,
    }
    assert manifest["corpus"]["ignored_columns_one_based"] == [10, 11, 12]

    evaluation = manifest["evaluation"]
    assert evaluation["required_components"] == [
        "rule",
        "ai_stalwart",
        "ai_gan_ae",
        "ai_isolation_forest",
        "ai_dual_confirm",
        "ai_feature_arbitration",
    ]
    assert evaluation["required_sensors"] == [f"S{index:02d}" for index in range(1, 9)]
    assert evaluation["splitter"] == {
        "method": "StratifiedKFold",
        "unit": "recording_id",
        "stratify_by": "vibration_case",
        "n_splits": 5,
        "shuffle": True,
        "random_state": 42,
    }
    assert evaluation["baseline_feed_order"] == ["timestamp", "sensor_id"]
    assert evaluation["evaluation_feed_order"] == ["timestamp", "sensor_id"]
    assert evaluation["snapshot_scope"] == {
        "capture_after": (
            "all out-of-fold INT recordings processed and pending refits completed"
        ),
        "include": [
            "baseline_learner_state",
            "ema_state",
            "rolling_windows",
            "fitted_isolation_forest_models",
            "score_calibration",
            "gan_ae_distribution_state",
            "voting_configuration",
        ],
        "reset_per_recording": [
            "engine_latest_state",
            "engine_history",
            "retained_alerts",
            "alert_cooldowns",
            "detector_failure_counters",
            "detector_detection_counters",
            "pending_refit_jobs",
        ],
    }
    assert manifest["checksums"] == {
        "conversion_source": "source.sha256",
        "evaluation_input": "normalized_csv.sha256",
    }
    assert manifest["artifacts"]["include"] == [
        "environment",
        "code_version",
        "threshold_profile_version",
        "source_identity",
        "dataset_sha256",
        "reproduction_command",
        "fold_assignments",
        "sample_counts",
        "metrics",
        "exit_reason",
    ]


def test_enhanced_vba_artifact_reports_compensation_reliability_calibration():
    path = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "vba"
        / "enhanced-v1.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    calibration = payload["calibration"]["synthetic_compensation_reliability"]
    assert calibration["scope"].startswith("synthetic fixtures")
    bins = calibration["bins"]
    assert bins
    assert set(bins) <= {"low", "medium", "high"}
    assert all(bin_payload["samples"] > 0 for bin_payload in bins.values())
