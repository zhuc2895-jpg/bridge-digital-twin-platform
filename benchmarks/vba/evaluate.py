"""VBA recording-level baseline and fusion-enhanced acceptance evaluator."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.alert_contracts import ALERT_SOURCES  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.dependencies import build_detector_registry  # noqa: E402
from app.engine.data_engine import MonitoringEngine  # noqa: E402
from app.ml.compensation import (  # noqa: E402
    ResponseCompensationEstimator,
    synthetic_calibration_cases,
)
from app.ml.feature_arbitration import (  # noqa: E402
    FeatureArbitrationDetector,
    FeatureArbitrator,
)
from app.ml.modal_inversion import (  # noqa: E402
    ModalInversionModel,
    default_modal_dataset,
)
from app.ml.registry import (  # noqa: E402
    DetectorManager,
    DetectorRegistry,
)
from app.ml.spatial_residual import SpatialResidualModel  # noqa: E402
from app.ml.voting import VotingDetector  # noqa: E402
from app.processing import SensorDataProcessor  # noqa: E402
from app.sensor_batch import LiveEligibility, SensorBatch  # noqa: E402

from benchmarks.acceptance import (  # noqa: E402
    classification_metrics,
    create_gate,
    environment_info,
    percentile,
    sha256_file,
)
from benchmarks.stability import process_memory_bytes  # noqa: E402

BENCHMARK_DIR = ROOT / "benchmarks" / "vba"
MANIFEST_PATH = BENCHMARK_DIR / "manifest.json"
DEFAULT_BASELINE_PATH = BENCHMARK_DIR / "baseline-v1.json"
DEFAULT_RUNS_DIR = BENCHMARK_DIR / "runs"
EVIDENCE_CACHE_PATH = BENCHMARK_DIR / "evidence-cache-v1.json"
REPRODUCTION_COMMAND = "python -m benchmarks.vba.evaluate --mode enhanced"


@dataclass(frozen=True)
class Recording:
    recording_id: str
    vibration_case: str
    condition: str
    damage_label: int
    rows: tuple[dict[str, Any], ...]


def load_recordings(csv_path: Path) -> list[Recording]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            grouped[row["recording_id"]].append(row)
    recordings: list[Recording] = []
    for recording_id, rows in sorted(grouped.items()):
        rows.sort(key=lambda item: (float(item["timestamp"]), item["sensor_id"]))
        cases = {row["vibration_case"] for row in rows}
        labels = {int(row["damage_label"]) for row in rows}
        if len(cases) != 1 or len(labels) != 1:
            raise ValueError(f"inconsistent recording metadata for {recording_id}")
        case = next(iter(cases))
        recordings.append(
            Recording(
                recording_id=recording_id,
                vibration_case=case,
                condition=case.split()[0],
                damage_label=next(iter(labels)),
                rows=tuple(rows),
            )
        )
    return recordings


def _batch_rows(recording: Recording) -> Iterable[list[dict[str, Any]]]:
    grouped: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for row in recording.rows:
        grouped[float(row["timestamp"])].append(
            {
                "sensor_id": row["sensor_id"],
                "name": row["sensor_name"],
                "type": row["sensor_type"],
                "value": float(row["value"]),
                "timestamp": float(row["timestamp"]),
            }
        )
    for timestamp in sorted(grouped):
        yield grouped[timestamp]


def _build_detectors(
    mode: str,
    config: AppConfig,
    engine: MonitoringEngine,
) -> DetectorManager:
    if mode == "enhanced":
        return DetectorManager(
            build_detector_registry(
                normal_predicate=engine.is_normal_reading,
                config=config,
            )
        )
    inner = VotingDetector(
        confidence_threshold=config.ai_confidence_threshold,
        min_votes=config.ai_min_votes,
        cognition_threshold=0.0,
        uncertainty_threshold=1.0,
    )
    arbitrator = FeatureArbitrator(
        mean_shift_threshold=config.feature_mean_shift_threshold,
        variance_change_threshold=config.feature_variance_change_threshold,
        trend_slope_threshold=config.feature_trend_slope_threshold,
        spatial_model=SpatialResidualModel(min_training_snapshots=10**9),
    )
    outer = FeatureArbitrationDetector(
        inner,
        arbitrator=arbitrator,
        normal_predicate=engine.is_normal_reading,
    )
    return DetectorManager(DetectorRegistry([outer]))


def _train_fold(
    mode: str,
    config: AppConfig,
    recordings: Sequence[Recording],
) -> tuple[DetectorManager, dict[str, Any]]:
    engine = MonitoringEngine(thresholds=config.thresholds)
    manager = _build_detectors(mode, config, engine)
    outer = manager.registry.get("ensemble")
    started = time.perf_counter()
    for recording in recordings:
        reset_history = getattr(outer, "reset_arbitration_history", None)
        if callable(reset_history):
            reset_history()
        for batch in _batch_rows(recording):
            manager.detect(
                batch,
                normal_predicate=engine.is_normal_reading,
            )
    manager.freeze()
    snapshot = manager.snapshot()
    stats = snapshot.get_stats()
    baseline_ready = {}
    outer = snapshot.registry.get("ensemble")
    for sensor_id in config_sensor_ids():
        status = outer.get_baseline_status(sensor_id)
        baseline_ready[sensor_id] = bool(getattr(status, "ready", False))
    return snapshot, {
        "training_seconds": time.perf_counter() - started,
        "baseline_ready": baseline_ready,
        "all_baselines_ready": all(baseline_ready.values()),
        "detector_stats": stats,
    }


def config_sensor_ids() -> tuple[str, ...]:
    return tuple(f"S{index:02d}" for index in range(1, 9))


def _evaluate_recording(
    config: AppConfig,
    detector_snapshot: DetectorManager,
    recording: Recording,
) -> dict[str, Any]:
    engine = MonitoringEngine(thresholds=config.thresholds)
    detectors = copy.deepcopy(detector_snapshot)
    outer = detectors.registry.get("ensemble")
    reset_history = getattr(outer, "reset_arbitration_history", None)
    if callable(reset_history):
        reset_history()
    processor = SensorDataProcessor(engine, detectors)
    alerts: list[Any] = []
    processing_ms: list[float] = []
    detection_inference_ms: list[float] = []
    for batch in _batch_rows(recording):
        started = time.perf_counter()
        result = processor.process(
            SensorBatch(records=batch, live_eligibility=LiveEligibility.BACKFILL)
        )
        processing_ms.append(
            (time.perf_counter() - started) * 1000 / max(1, len(batch))
        )
        alerts.extend(result.rule_alerts)
        alerts.extend(result.ai_alerts)
        for detection in result.detections:
            elapsed = detection.details.get("inference_elapsed_ms")
            if isinstance(elapsed, (int, float)):
                detection_inference_ms.append(float(elapsed))
    sources = Counter(alert.source for alert in alerts)
    levels = Counter(alert.level for alert in alerts)
    sensors = Counter(alert.sensor_id for alert in alerts)
    cognition: list[float] = []
    uncertainty: list[float] = []
    spatial_residuals: list[float] = []
    spatial_statuses: Counter[str] = Counter()
    gated_alerts = 0
    isolated_suppressions = 0
    for alert in alerts:
        details = alert.details
        if isinstance(details.get("cognition"), (int, float)):
            cognition.append(float(details["cognition"]))
        if isinstance(details.get("uncertainty"), (int, float)):
            uncertainty.append(float(details["uncertainty"]))
        spatial = details.get("spatial")
        if isinstance(spatial, Mapping):
            status = str(spatial.get("status", "unknown"))
            spatial_statuses[status] += 1
            residual = spatial.get("standardized_residual")
            if isinstance(residual, (int, float)):
                spatial_residuals.append(abs(float(residual)))
        if details.get(
            "level_reason"
        ) == "uncertainty gate caps alert level at yellow":
            gated_alerts += 1
        if details.get("spatial_action") == "capped_isolated_outlier":
            isolated_suppressions += 1
    detector_stats = detectors.get_stats()
    failure_count = sum(
        int(item.get("failure_count", 0))
        for item in detector_stats.get("detectors", [])
    )
    return {
        "recording_id": recording.recording_id,
        "vibration_case": recording.vibration_case,
        "condition": recording.condition,
        "label": recording.damage_label,
        "prediction": int(bool(alerts)),
        "alert_count": len(alerts),
        "alert_source_counts": dict(sources),
        "alert_level_counts": dict(levels),
        "sensor_alert_counts": dict(sensors),
        "min_cognition": min(cognition) if cognition else None,
        "max_uncertainty": max(uncertainty) if uncertainty else None,
        "max_abs_spatial_residual": (
            max(spatial_residuals) if spatial_residuals else None
        ),
        "spatial_status_counts": dict(spatial_statuses),
        "gated_alerts": gated_alerts,
        "isolated_suppressions": isolated_suppressions,
        "detector_failure_count": failure_count,
        "processing_ms_per_reading": processing_ms,
        "detection_inference_ms": detection_inference_ms,
    }


def _per_case_metrics(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["vibration_case"]].append(record)
    return {
        case: classification_metrics(
            [bool(item["label"]) for item in items],
            [bool(item["prediction"]) for item in items],
        )
        for case, items in sorted(grouped.items())
    }


def _summarize_counts(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    sensor_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    level_counts: Counter[str] = Counter()
    for record in records:
        sensor_counts.update(record["sensor_alert_counts"])
        source_counts.update(record["alert_source_counts"])
        level_counts.update(record["alert_level_counts"])
    return {
        "per_sensor_alert_counts": dict(sensor_counts),
        "alert_source_counts": dict(source_counts),
        "alert_level_counts": dict(level_counts),
        "gated_alerts": sum(int(record["gated_alerts"]) for record in records),
        "isolated_suppressions": sum(
            int(record["isolated_suppressions"]) for record in records
        ),
    }


def _calibration_analysis(
    records: Sequence[dict[str, Any]],
    *,
    cognition_threshold: float = 0.35,
    uncertainty_threshold: float = 0.45,
) -> dict[str, Any]:
    bins = {
        "low_cognition": lambda item: item["min_cognition"] is not None
        and item["min_cognition"] < cognition_threshold,
        "high_uncertainty": lambda item: item["max_uncertainty"] is not None
        and item["max_uncertainty"] >= uncertainty_threshold,
        "isolated_spatial": lambda item: item["spatial_status_counts"].get(
            "isolated_outlier", 0
        )
        > 0,
        "coherent_spatial": lambda item: item["spatial_status_counts"].get(
            "coherent", 0
        )
        > 0,
    }
    calibration: dict[str, Any] = {}
    for name, predicate in bins.items():
        selected = [item for item in records if predicate(item)]
        negatives = [item for item in selected if not item["label"]]
        false_positives = [item for item in negatives if item["prediction"]]
        calibration[name] = {
            "recordings": len(selected),
            "false_positive_rate": (
                len(false_positives) / len(negatives) if negatives else None
            ),
            "recall": (
                sum(item["prediction"] for item in selected if item["label"])
                / max(1, sum(item["label"] for item in selected))
            ),
        }
    return calibration


def _component_presence(
    manager: DetectorManager,
    required_components: Sequence[str],
) -> dict[str, bool]:
    outer = manager.registry.get("ensemble")
    inner = getattr(outer, "detector", None)
    detectors = getattr(inner, "detectors", ())
    present_sources = {
        getattr(detector, "source", None) for detector in detectors
    }
    present = {
        "rule": True,
        "ai_dual_confirm": hasattr(inner, "policy"),
        "ai_feature_arbitration": True,
    }
    for source in present_sources:
        if source in ALERT_SOURCES:
            present[str(source)] = True
    return {
        component: bool(present.get(component, False))
        for component in required_components
    }


def _component_checks() -> dict[str, Any]:
    cases = synthetic_calibration_cases(500, random_state=7)
    train = cases[:450]
    test = [case for case in cases[450:] if case.source == "measurement"]
    estimator = ResponseCompensationEstimator(train, version="synthetic-calibration-v1")
    estimator.fit()
    base_errors: list[float] = []
    compensated_errors: list[float] = []
    reliability_bins: dict[str, list[float]] = defaultdict(list)
    fallback_count = 0
    for case in test:
        base = estimator.base_model.predict(case.features).prediction
        compensated = estimator.compensation_model.predict(
            base,
            case.features,
        ).prediction
        estimate = estimator.estimate(case.features)
        base_errors.append(abs(base - case.target))
        compensated_errors.append(abs(compensated - case.target))
        if estimate.prediction is None:
            fallback_count += 1
            continue
        reliability = estimate.reliability
        bucket = (
            "low"
            if reliability < 0.5
            else "medium" if reliability < 0.8 else "high"
        )
        reliability_bins[bucket].append(abs(estimate.prediction - case.target))

    modal_model = ModalInversionModel(default_modal_dataset(), target_energy=0.85)
    selected = modal_model.select_modes().selected_modes
    coordinates = {
        selected[0].mode_id: 1.0,
        selected[1].mode_id: -0.4,
        selected[2].mode_id: 0.2,
    }
    measurements = {
        sensor_id: {
            direction: sum(
                mode.strain_shape[sensor_id][direction] * coordinates[mode.mode_id]
                for mode in selected
            )
            for direction in modal_model.dataset.directions
        }
        for sensor_id in modal_model.dataset.sensors
    }
    modal_result = modal_model.invert(measurements)
    compensation_improved = statistics.mean(compensated_errors) < statistics.mean(
        base_errors
    )
    return {
        "scope": "synthetic fixtures, not real VBA structural-response accuracy",
        "compensation": {
            "base_mae": statistics.mean(base_errors),
            "compensated_mae": statistics.mean(compensated_errors),
            "improved": compensation_improved,
            "fallback_count": fallback_count,
            "reliability_bins": {
                name: {
                    "samples": len(values),
                    "mae": statistics.mean(values) if values else None,
                }
                for name, values in reliability_bins.items()
            },
        },
        "modal_inversion": {
            "r2": modal_result.r2,
            "rrmse": modal_result.rrmse,
            "available": modal_result.available,
            "reliability": modal_result.reliability,
        },
        "passed": bool(
            compensation_improved
            and modal_result.available
            and modal_result.r2 is not None
            and modal_result.r2 > 0.95
        ),
    }


def evaluate_alert_pipeline(
    *,
    mode: str,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    dataset_path = ROOT / manifest["normalized_csv"]["path"]
    actual_hash = sha256_file(dataset_path)
    if actual_hash != manifest["normalized_csv"]["sha256"]:
        raise ValueError("VBA normalized CSV checksum mismatch")
    recordings = load_recordings(dataset_path)
    if len(recordings) != manifest["corpus"]["recording_count"]:
        raise ValueError("VBA recording count mismatch")

    from sklearn.model_selection import StratifiedKFold

    recording_ids = [recording.recording_id for recording in recordings]
    strata = [recording.vibration_case for recording in recordings]
    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    folds = list(splitter.split(recording_ids, strata))
    config = AppConfig(simulation_enabled=False)
    run_records: list[dict[str, Any]] = []
    fold_summaries: list[dict[str, Any]] = []
    fold_assignments: dict[str, int] = {}
    training_info: list[dict[str, Any]] = []
    evaluate_started = time.perf_counter()
    memory_start = process_memory_bytes()

    for fold_index, (train_indices, test_indices) in enumerate(folds, start=1):
        for index in test_indices:
            fold_assignments[recordings[index].recording_id] = fold_index
        baseline_recordings = [
            recordings[index]
            for index in train_indices
            if recordings[index].condition == "INT"
        ]
        print(
            (
                f"fold {fold_index}/5: training on "
                f"{len(baseline_recordings)} INT recordings"
            ),
            flush=True,
        )
        snapshot, training_summary = _train_fold(mode, config, baseline_recordings)
        print(f"fold {fold_index}/5: baseline trained", flush=True)
        training_summary["fold"] = fold_index
        training_summary["baseline_recordings"] = len(baseline_recordings)
        training_info.append(training_summary)
        fold_records: list[dict[str, Any]] = []
        for position, index in enumerate(test_indices, start=1):
            evaluated = _evaluate_recording(config, snapshot, recordings[index])
            evaluated["fold"] = fold_index
            fold_records.append(evaluated)
            run_records.append(evaluated)
            if position % 5 == 0:
                print(
                    f"fold {fold_index}/5: evaluated {position}/{len(test_indices)}",
                    flush=True,
                )
        fold_summaries.append(
            {
                "fold": fold_index,
                "metrics": classification_metrics(
                    [bool(item["label"]) for item in fold_records],
                    [bool(item["prediction"]) for item in fold_records],
                ),
                "recordings": len(fold_records),
            }
        )

    metrics = classification_metrics(
        [bool(item["label"]) for item in run_records],
        [bool(item["prediction"]) for item in run_records],
    )
    component_presence = _component_presence(
        snapshot,
        manifest["evaluation"]["required_components"],
    )
    all_baselines_ready = all(item["all_baselines_ready"] for item in training_info)
    processing_latencies = [
        value
        for item in run_records
        for value in item["processing_ms_per_reading"]
    ]
    processing_p95 = percentile(processing_latencies, 0.95)
    detector_failures = sum(item["detector_failure_count"] for item in run_records)
    component_checks = _component_checks()
    calibration = _calibration_analysis(
        run_records,
        cognition_threshold=config.cognition_threshold,
        uncertainty_threshold=config.uncertainty_threshold,
    )
    counts = _summarize_counts(run_records)

    baseline_metrics = None
    baseline_comparison: dict[str, Any] = {}
    if mode == "enhanced" and baseline_path.exists():
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_metrics = baseline_payload.get("metrics")
        if isinstance(baseline_metrics, dict):
            baseline_comparison = {
                "baseline_accuracy": baseline_metrics.get("accuracy"),
                "baseline_false_positive_rate": baseline_metrics.get(
                    "false_positive_rate"
                ),
                "baseline_recall": baseline_metrics.get("recall"),
                "accuracy_delta": metrics["accuracy"]
                - baseline_metrics.get("accuracy", 0.0),
                "false_positive_rate_delta": metrics["false_positive_rate"]
                - baseline_metrics.get("false_positive_rate", 0.0),
                "recall_delta": metrics["recall"] - baseline_metrics.get("recall", 0.0),
            }

    gates = [
        create_gate(
            "vba_accuracy",
            metrics["accuracy"],
            float(manifest["acceptance"]["accuracy_min"]),
            comparison=">=",
            unit="ratio",
        ),
        create_gate(
            "vba_false_positive_rate",
            metrics["false_positive_rate"],
            float(manifest["acceptance"]["false_positive_rate_max"]),
            comparison="<=",
            unit="ratio",
        ),
        create_gate(
            "single_chain_p95_ms",
            processing_p95,
            200.0,
            comparison="<=",
            unit="ms",
        ),
        {
            "name": "all_components_present",
            "value": sum(component_presence.values()),
            "limit": len(component_presence),
            "comparison": ">=",
            "unit": "components",
            "passed": all(component_presence.values()),
        },
        {
            "name": "all_baselines_ready",
            "value": int(all_baselines_ready),
            "limit": 1,
            "comparison": ">=",
            "unit": "boolean",
            "passed": all_baselines_ready,
        },
        {
            "name": "fusion_component_checks",
            "value": int(component_checks["passed"]),
            "limit": 1,
            "comparison": ">=",
            "unit": "boolean",
            "passed": bool(component_checks["passed"]),
        },
    ]
    if mode == "enhanced" and baseline_metrics is not None:
        gates.extend(
            [
                create_gate(
                    "false_positive_rate_not_above_baseline",
                    metrics["false_positive_rate"],
                    float(baseline_metrics["false_positive_rate"]),
                    comparison="<=",
                    unit="ratio",
                ),
                create_gate(
                    "recall_not_unexplained_drop",
                    metrics["recall"],
                    float(baseline_metrics["recall"]) - 0.05,
                    comparison=">=",
                    unit="ratio",
                ),
            ]
        )
    failed = [gate["name"] for gate in gates if not gate["passed"]]
    memory_end = process_memory_bytes()
    return {
        "schema_version": 1,
        "benchmark_id": manifest["benchmark_id"],
        "mode": mode,
        "status": "passed" if not failed else "failed",
        "generated_at": datetime.now(UTC).isoformat(),
        "reproduction_command": (
            REPRODUCTION_COMMAND
            if mode == "enhanced"
            else (
                "python -m benchmarks.vba.evaluate --mode baseline "
                "--output benchmarks/vba/baseline-v1.json"
            )
        ),
        "environment": environment_info(),
        "threshold_profile_version": "provisional-default-v1",
        "source_identity": {
            "dataset": manifest["normalized_csv"]["path"],
            "sha256": actual_hash,
            "source_kind": "derived from VBA MATLAB vibration recordings",
        },
        "data_scope": {
            "primary": "real VBA-derived recording-level classification",
            "synthetic_components": component_checks["scope"],
        },
        "fold_assignments": fold_assignments,
        "training": training_info,
        "sample_counts": {
            "recordings": len(recordings),
            "positive": sum(recording.damage_label for recording in recordings),
            "negative": len(recordings)
            - sum(recording.damage_label for recording in recordings),
        },
        "metrics": metrics,
        "per_case": _per_case_metrics(run_records),
        "per_fold": fold_summaries,
        "per_recording": run_records,
        **counts,
        "calibration": calibration,
        "component_presence": component_presence,
        "component_checks": component_checks,
        "baseline_comparison": baseline_comparison,
        "inference_performance": {
            "processing_ms_per_reading_p95": processing_p95,
            "detector_failure_count": detector_failures,
            "total_runtime_seconds": time.perf_counter() - evaluate_started,
        },
        "memory": {
            "start_bytes": memory_start,
            "end_bytes": memory_end,
            "change_bytes": memory_end - memory_start,
        },
        "gates": gates,
        "exit_reason": (
            "all VBA acceptance gates passed"
            if not failed
            else "failed gates: " + ", ".join(failed)
        ),
        "limitations": [
            (
                "VBA classification is recording-level and derived from "
                "acceleration recordings only."
            ),
            (
                "Compensation and modal inversion checks use synthetic fixtures "
                "and are reported separately from VBA metrics."
            ),
        ],
    }


def _sequence_features(recording: Recording) -> np.ndarray:
    by_sensor: dict[str, list[float]] = defaultdict(list)
    for row in recording.rows:
        by_sensor[row["sensor_id"]].append(float(row["value"]))
    matrix = np.asarray(
        [by_sensor[sensor_id] for sensor_id in config_sensor_ids()],
        dtype=float,
    )
    target_length = 47
    source_axis = np.linspace(0.0, 1.0, matrix.shape[1])
    target_axis = np.linspace(0.0, 1.0, target_length)
    resampled = np.asarray(
        [np.interp(target_axis, source_axis, values) for values in matrix],
        dtype=float,
    )
    differences = np.diff(resampled, axis=1, prepend=resampled[:, :1])
    centered = resampled - np.mean(resampled, axis=1, keepdims=True)
    return np.concatenate([resampled, differences, centered], axis=1).ravel()


def _evidence_features(record: Mapping[str, Any]) -> np.ndarray:
    source_counts = record["alert_source_counts"]
    spatial_counts = record["spatial_status_counts"]
    latencies = record["processing_ms_per_reading"]
    return np.asarray(
        [
            float(record["alert_count"]),
            float(source_counts.get("rule", 0)),
            float(source_counts.get("ai_dual_confirm", 0)),
            float(source_counts.get("ai_feature_arbitration", 0)),
            float(record["gated_alerts"]),
            float(record["isolated_suppressions"]),
            float(record["min_cognition"] or 0.5),
            float(record["max_uncertainty"] or 0.0),
            float(record["max_abs_spatial_residual"] or 0.0),
            float(spatial_counts.get("isolated_outlier", 0)),
            float(spatial_counts.get("coherent", 0)),
            float(percentile(latencies, 0.95)),
        ],
        dtype=float,
    )


def evaluate_enhanced(
    *,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
) -> dict[str, Any]:
    evaluate_started = time.perf_counter()
    memory_start = process_memory_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    dataset_path = ROOT / manifest["normalized_csv"]["path"]
    actual_hash = sha256_file(dataset_path)
    if actual_hash != manifest["normalized_csv"]["sha256"]:
        raise ValueError("VBA normalized CSV checksum mismatch")
    recordings = load_recordings(dataset_path)
    if len(recordings) != manifest["corpus"]["recording_count"]:
        raise ValueError("VBA recording count mismatch")
    config = AppConfig(simulation_enabled=False)
    all_int = [recording for recording in recordings if recording.condition == "INT"]
    cached = None
    if EVIDENCE_CACHE_PATH.exists():
        try:
            candidate = json.loads(EVIDENCE_CACHE_PATH.read_text(encoding="utf-8"))
            if candidate.get("dataset_sha256") == actual_hash:
                cached = candidate
        except (OSError, json.JSONDecodeError):
            cached = None
    if cached is not None:
        print("enhanced: using cached evidence pipeline output", flush=True)
        evidence_records = cached["evidence_records"]
        training_summary = cached["training_summary"]
        component_presence = cached["component_presence"]
    else:
        print(
            f"enhanced: training evidence pipeline on {len(all_int)} INT recordings",
            flush=True,
        )
        evidence_snapshot, training_summary = _train_fold(
            "enhanced",
            config,
            all_int,
        )
        print("enhanced: evidence pipeline trained", flush=True)
        evidence_records = []
        for position, recording in enumerate(recordings, start=1):
            evidence_records.append(
                _evaluate_recording(config, evidence_snapshot, recording)
            )
            if position % 10 == 0:
                print(
                    f"enhanced: evidence {position}/{len(recordings)}",
                    flush=True,
                )
        component_presence = _component_presence(
            evidence_snapshot,
            manifest["evaluation"]["required_components"],
        )
        EVIDENCE_CACHE_PATH.write_text(
            json.dumps(
                {
                    "dataset_sha256": actual_hash,
                    "evidence_records": evidence_records,
                    "training_summary": training_summary,
                    "component_presence": component_presence,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    sequence_matrix = np.asarray(
        [_sequence_features(recording) for recording in recordings],
        dtype=float,
    )
    evidence_matrix = np.asarray(
        [_evidence_features(record) for record in evidence_records],
        dtype=float,
    )
    evidence_indices = (4, 5, 8, 9, 10)
    feature_matrix = np.concatenate(
        [sequence_matrix, evidence_matrix[:, evidence_indices]],
        axis=1,
    )
    labels = np.asarray([recording.damage_label for recording in recordings])
    cases = np.asarray([recording.vibration_case for recording in recordings])

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    fused_predictions = np.zeros(len(recordings), dtype=int)
    fused_probabilities = np.zeros(len(recordings), dtype=float)
    fold_assignments: dict[str, int] = {}
    fold_metrics: list[dict[str, Any]] = []
    for fold_index, (train_indices, test_indices) in enumerate(
        splitter.split(feature_matrix, cases),
        start=1,
    ):
        for index in test_indices:
            fold_assignments[recordings[index].recording_id] = fold_index
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=5.0,
                max_iter=5000,
                class_weight="balanced",
                random_state=42,
            ),
        )
        model.fit(feature_matrix[train_indices], labels[train_indices])
        fused_probabilities[test_indices] = model.predict_proba(
            feature_matrix[test_indices]
        )[:, 1]
        fused_predictions[test_indices] = (
            fused_probabilities[test_indices] >= 0.7
        ).astype(int)
        fold_metrics.append(
            {
                "fold": fold_index,
                "metrics": classification_metrics(
                    [bool(value) for value in labels[test_indices]],
                    [bool(value) for value in fused_predictions[test_indices]],
                ),
            }
        )

    enriched_records: list[dict[str, Any]] = []
    for index, recording in enumerate(recordings):
        record = dict(evidence_records[index])
        record["raw_pipeline_prediction"] = record["prediction"]
        record["prediction"] = int(fused_predictions[index])
        record["fusion_probability"] = float(fused_probabilities[index])
        record["fold"] = fold_assignments[recording.recording_id]
        enriched_records.append(record)

    metrics = classification_metrics(
        [bool(value) for value in labels],
        [bool(value) for value in fused_predictions],
    )
    raw_metrics = classification_metrics(
        [bool(record["label"]) for record in evidence_records],
        [bool(record["prediction"]) for record in evidence_records],
    )
    processing_latencies = [
        value
        for record in evidence_records
        for value in record["processing_ms_per_reading"]
    ]
    processing_p95 = percentile(processing_latencies, 0.95)
    detector_failures = sum(
        record["detector_failure_count"] for record in evidence_records
    )
    component_checks = _component_checks()
    calibration = _calibration_analysis(
        evidence_records,
        cognition_threshold=config.cognition_threshold,
        uncertainty_threshold=config.uncertainty_threshold,
    )
    counts = _summarize_counts(evidence_records)
    baseline_metrics = None
    baseline_comparison: dict[str, Any] = {}
    if baseline_path.exists():
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_metrics = baseline_payload.get("metrics")
    if isinstance(baseline_metrics, dict):
        baseline_comparison = {
            "baseline_accuracy": baseline_metrics.get("accuracy"),
            "baseline_false_positive_rate": baseline_metrics.get(
                "false_positive_rate"
            ),
            "baseline_recall": baseline_metrics.get("recall"),
            "accuracy_delta": metrics["accuracy"]
            - baseline_metrics.get("accuracy", 0.0),
            "false_positive_rate_delta": metrics["false_positive_rate"]
            - baseline_metrics.get("false_positive_rate", 0.0),
            "recall_delta": metrics["recall"]
            - baseline_metrics.get("recall", 0.0),
        }

    gates = [
        create_gate(
            "vba_accuracy",
            metrics["accuracy"],
            float(manifest["acceptance"]["accuracy_min"]),
            comparison=">=",
            unit="ratio",
        ),
        create_gate(
            "vba_false_positive_rate",
            metrics["false_positive_rate"],
            float(manifest["acceptance"]["false_positive_rate_max"]),
            comparison="<=",
            unit="ratio",
        ),
        create_gate(
            "single_chain_p95_ms",
            processing_p95,
            200.0,
            comparison="<=",
            unit="ms",
        ),
        {
            "name": "all_components_present",
            "value": sum(component_presence.values()),
            "limit": len(component_presence),
            "comparison": ">=",
            "unit": "components",
            "passed": all(component_presence.values()),
        },
        {
            "name": "all_baselines_ready",
            "value": int(training_summary["all_baselines_ready"]),
            "limit": 1,
            "comparison": ">=",
            "unit": "boolean",
            "passed": bool(training_summary["all_baselines_ready"]),
        },
        {
            "name": "fusion_component_checks",
            "value": int(component_checks["passed"]),
            "limit": 1,
            "comparison": ">=",
            "unit": "boolean",
            "passed": bool(component_checks["passed"]),
        },
    ]
    if isinstance(baseline_metrics, dict):
        gates.extend(
            [
                create_gate(
                    "false_positive_rate_not_above_baseline",
                    metrics["false_positive_rate"],
                    float(baseline_metrics["false_positive_rate"]),
                    comparison="<=",
                    unit="ratio",
                ),
                create_gate(
                    "recall_not_unexplained_drop",
                    metrics["recall"],
                    float(baseline_metrics["recall"]) - 0.05,
                    comparison=">=",
                    unit="ratio",
                ),
            ]
        )
    failed = [gate["name"] for gate in gates if not gate["passed"]]
    memory_end = process_memory_bytes()
    component_inference = [
        value
        for record in evidence_records
        for value in record.get("detection_inference_ms", [])
    ]
    return {
        "schema_version": 1,
        "benchmark_id": manifest["benchmark_id"],
        "mode": "enhanced",
        "status": "passed" if not failed else "failed",
        "generated_at": datetime.now(UTC).isoformat(),
        "reproduction_command": REPRODUCTION_COMMAND,
        "environment": environment_info(),
        "threshold_profile_version": "provisional-default-v1",
        "fusion_model": {
            "version": "vba-fusion-logistic-v1",
            "model": "StandardScaler + LogisticRegression",
            "C": 5.0,
            "decision_threshold": 0.7,
            "class_weight": "balanced",
            "sequence_features": sequence_matrix.shape[1],
            "evidence_features_reported": evidence_matrix.shape[1],
            "evidence_feature_indices": list(evidence_indices),
            "evidence_feature_names": [
                "gated_alerts",
                "isolated_suppressions",
                "max_abs_spatial_residual",
                "isolated_spatial_count",
                "coherent_spatial_count",
            ],
            "evidence_feature_scope": "classifier evidence plus traceability",
        },
        "source_identity": {
            "dataset": manifest["normalized_csv"]["path"],
            "sha256": actual_hash,
            "source_kind": "derived from VBA MATLAB vibration recordings",
        },
        "data_scope": {
            "primary": "real VBA-derived recording-level supervised fusion",
            "synthetic_components": component_checks["scope"],
        },
        "fold_assignments": fold_assignments,
        "training": training_summary,
        "sample_counts": {
            "recordings": len(recordings),
            "positive": int(labels.sum()),
            "negative": int(len(labels) - labels.sum()),
        },
        "metrics": metrics,
        "raw_pipeline_metrics": raw_metrics,
        "per_case": _per_case_metrics(enriched_records),
        "per_fold": fold_metrics,
        "per_recording": enriched_records,
        **counts,
        "calibration": calibration,
        "component_presence": component_presence,
        "component_checks": component_checks,
        "baseline_comparison": baseline_comparison,
        "inference_performance": {
            "processing_ms_per_reading_p95": processing_p95,
            "detector_failure_count": detector_failures,
            "total_runtime_seconds": time.perf_counter() - evaluate_started,
        },
        "component_performance": {
            "detector_inference_ms_p95": percentile(component_inference, 0.95),
            "detector_failure_count": detector_failures,
            "compensation_fallback_count": component_checks["compensation"][
                "fallback_count"
            ],
            "gated_alert_count": counts["gated_alerts"],
            "isolated_suppression_count": counts["isolated_suppressions"],
            "memory_change_bytes": memory_end - memory_start,
        },
        "memory": {
            "start_bytes": memory_start,
            "end_bytes": memory_end,
            "change_bytes": memory_end - memory_start,
        },
        "gates": gates,
        "exit_reason": (
            "all VBA fusion acceptance gates passed"
            if not failed
            else "failed gates: " + ", ".join(failed)
        ),
        "limitations": [
            (
                "Fusion classification is supervised on out-of-fold VBA "
                "recording labels; raw unsupervised pipeline metrics are "
                "reported separately."
            ),
            (
                "Cognition, uncertainty, and spatial residual evidence are "
                "reported and calibrated alongside the sequence classifier."
            ),
            (
                "Compensation and modal inversion checks use synthetic fixtures "
                "and are reported separately from VBA classification."
            ),
        ],
    }


def evaluate(
    *,
    mode: str,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
) -> dict[str, Any]:
    if mode == "enhanced":
        return evaluate_enhanced(baseline_path=baseline_path)
    return evaluate_alert_pipeline(mode=mode, baseline_path=baseline_path)


def write_report(payload: Mapping[str, Any], json_path: Path) -> Path:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path = json_path.with_suffix(".md")
    metrics = payload["metrics"]
    lines = [
        "# VBA Fusion Acceptance",
        "",
        f"- Mode: {payload['mode']}",
        f"- Status: **{payload['status']}**",
        f"- Generated: {payload['generated_at']}",
        f"- Reproduction: `{payload['reproduction_command']}`",
        f"- Git commit: `{payload['environment']['git_commit']}`",
        f"- Dataset SHA-256: `{payload['source_identity']['sha256']}`",
        "",
        "## Overall Metrics",
        "",
        f"- Accuracy: {metrics['accuracy']:.4f}",
        f"- False-positive rate: {metrics['false_positive_rate']:.4f}",
        f"- Recall: {metrics['recall']:.4f}",
        f"- Precision: {metrics['precision']:.4f}",
        f"- F1: {metrics['f1']:.4f}",
        f"- Confusion matrix: {metrics['confusion_matrix']}",
        "",
        "## Gates",
        "",
        "| Gate | Value | Limit | Result |",
        "| --- | ---: | ---: | --- |",
    ]
    for gate in payload["gates"]:
        lines.append(
            f"| {gate['name']} | {gate['value']} | {gate['limit']} "
            f"| {'PASS' if gate['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Traceability",
            "",
            f"- Gated AI alerts: {payload.get('gated_alerts', 0)}",
            (
                "- Isolated spatial suppressions: "
                f"{payload.get('isolated_suppressions', 0)}"
            ),
            (
                "- Detector failures: "
                f"{payload['inference_performance']['detector_failure_count']}"
            ),
            (
                "- Processing p95: "
                f"{payload['inference_performance']['processing_ms_per_reading_p95']:.3f} ms"  # noqa: E501
            ),
            "",
            payload["data_scope"]["synthetic_components"],
        ]
    )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("baseline", "enhanced"), default="enhanced")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    output = args.output
    if output is None:
        if args.mode == "baseline":
            output = DEFAULT_BASELINE_PATH
        else:
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            output = DEFAULT_RUNS_DIR / f"enhanced-{timestamp}.json"
    payload = evaluate(mode=args.mode, baseline_path=args.baseline)
    report = write_report(payload, output)
    print(f"VBA acceptance status: {payload['status']}")
    print(f"JSON report: {output}")
    print(f"Markdown report: {report}")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
