"""Reproducible system acceptance for performance, load, and validation metrics."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx
import uvicorn
import websockets

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import AppConfig  # noqa: E402
from app.engine.data_engine import MonitoringEngine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.sensor_batch import LiveEligibility, SensorBatch  # noqa: E402
from app.sensor_reading import SensorReadingRecord  # noqa: E402
from app.threshold_provenance import (  # noqa: E402
    DEFAULT_SENSOR_THRESHOLD_TYPES,
)

VALIDATION_MANIFEST = ROOT / "benchmarks" / "validation" / "manifest.json"
DEFAULT_RUNS_DIR = ROOT / "benchmarks" / "runs"
REPRODUCTION_COMMAND = "python -m benchmarks.acceptance"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def create_gate(
    name: str,
    value: float,
    limit: float,
    *,
    comparison: str,
    unit: str,
) -> dict[str, Any]:
    passed = value <= limit if comparison == "<=" else value >= limit
    return {
        "name": name,
        "value": value,
        "limit": limit,
        "comparison": comparison,
        "unit": unit,
        "passed": passed,
    }


def classification_metrics(
    labels: Sequence[bool],
    predictions: Sequence[bool],
) -> dict[str, Any]:
    if len(labels) != len(predictions):
        raise ValueError("labels and predictions must have equal length")
    tp = sum(
        label and prediction
        for label, prediction in zip(labels, predictions, strict=True)
    )
    tn = sum(
        not label and not prediction
        for label, prediction in zip(labels, predictions, strict=True)
    )
    fp = sum(
        not label and prediction
        for label, prediction in zip(labels, predictions, strict=True)
    )
    fn = sum(
        label and not prediction
        for label, prediction in zip(labels, predictions, strict=True)
    )
    total = len(labels)
    return {
        "samples": total,
        "accuracy": (tp + tn) / total if total else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "f1": (
            2 * tp / (2 * tp + fp + fn)
            if 2 * tp + fp + fn
            else 0.0
        ),
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
    }


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def running_server(config: AppConfig):
    port = _find_free_port()
    application = create_app(config=config)
    uvicorn_config = uvicorn.Config(
        application,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(uvicorn_config)
    thread = threading.Thread(target=server.run, name="acceptance-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        if not thread.is_alive():
            raise RuntimeError("acceptance server stopped during startup")
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("acceptance server did not start within 15 seconds")
    try:
        yield f"http://127.0.0.1:{port}", f"ws://127.0.0.1:{port}/ws/live"
    finally:
        server.should_exit = True
        thread.join(timeout=15)


def _records_10k() -> tuple[list[dict[str, Any]], float, float]:
    end = time.time()
    records: list[dict[str, Any]] = []
    for index in range(10_000):
        records.append(
            {
                "sensor_id": "S01",
                "name": "Main span strain",
                "type": "strain",
                "value": 100.0,
                "timestamp": end - (10_000 - index) * 0.1,
            }
        )
    return records, records[0]["timestamp"], records[-1]["timestamp"]


def _timed_get(
    client: httpx.Client,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    repeats: int = 5,
) -> list[float]:
    client.get(path, params=params).raise_for_status()
    values: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        response = client.get(path, params=params)
        values.append((time.perf_counter() - started) * 1000)
        response.raise_for_status()
    return values


def run_api_performance(temporary_root: Path) -> dict[str, Any]:
    config = AppConfig(
        simulation_enabled=False,
        checkpoint_path=temporary_root / "api-performance.json",
        log_level="WARNING",
    )
    records, start_ts, end_ts = _records_10k()
    with running_server(config) as (base_url, _):
        with httpx.Client(base_url=base_url, timeout=60) as client:
            started = time.perf_counter()
            response = client.post(
                "/api/data/upload/json",
                params={"push_live": "false"},
                json=records,
            )
            ingest_ms = (time.perf_counter() - started) * 1000
            response.raise_for_status()
            payload = response.json()
            if payload["records_ingested"] != 10_000:
                raise RuntimeError("10k ingestion returned an unexpected record count")

            latest = _timed_get(client, "/api/sensors/")
            history = _timed_get(
                client,
                "/api/sensors/history/range",
                params={
                    "sensor_id": "S01",
                    "start": start_ts,
                    "end": end_ts,
                    "max_points": 500,
                },
            )
            snapshot = _timed_get(
                client,
                "/api/sensors/history/snapshot",
                params={"ts": end_ts},
            )

    query_p95 = max(percentile(latest, 0.95), percentile(history, 0.95))
    snapshot_p95 = percentile(snapshot, 0.95)
    gates = [
        create_gate(
            "batch_ingest_10000_ms",
            ingest_ms,
            500,
            comparison="<=",
            unit="ms",
        ),
        create_gate(
            "regular_query_p95_ms",
            query_p95,
            200,
            comparison="<=",
            unit="ms",
        ),
        create_gate(
            "snapshot_p95_ms",
            snapshot_p95,
            100,
            comparison="<=",
            unit="ms",
        ),
    ]
    return {
        "ingest_ms": ingest_ms,
        "latest_ms": latest,
        "history_range_ms": history,
        "snapshot_ms": snapshot,
        "query_p95_ms": query_p95,
        "snapshot_p95_ms": snapshot_p95,
        "records": 10_000,
        "gates": gates,
    }


def run_detector_performance() -> dict[str, Any]:
    from app.dependencies import create_services

    config = AppConfig(simulation_enabled=False)
    services = create_services(config=config)
    services.live_stream_autostart = False
    baseline_start = time.time() - 300
    baseline: list[SensorReadingRecord] = [
        {
            "sensor_id": "S01",
            "name": "Main span strain",
            "type": "strain",
            "value": 100.0 + 2.0 * math.sin(index / 8),
            "timestamp": baseline_start + index,
        }
        for index in range(150)
    ]
    services.processor.process(SensorBatch(records=baseline))

    latencies: list[float] = []
    for index in range(5):
        candidate: SensorReadingRecord = {
            "sensor_id": "S01",
            "name": "Main span strain",
            "type": "strain",
            "value": 500.0 + index,
            "timestamp": baseline_start + 151 + index,
        }
        started = time.perf_counter()
        services.detectors.detect(
            [candidate],
            normal_predicate=services.engine.is_normal_reading,
        )
        latencies.append((time.perf_counter() - started) * 1000)
    p95 = percentile(latencies, 0.95)
    return {
        "latencies_ms": latencies,
        "p95_ms": p95,
        "baseline_readings": len(baseline),
        "gates": [
            create_gate(
                "three_layer_detection_p95_ms",
                p95,
                200,
                comparison="<=",
                unit="ms",
            )
        ],
    }


async def _api_load_workers(
    base_url: str,
    *,
    seconds: float = 5.0,
    concurrency: int = 20,
) -> dict[str, Any]:
    deadline = time.perf_counter() + seconds
    latencies: list[float] = []
    errors: list[str] = []

    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        async def worker() -> int:
            completed = 0
            while time.perf_counter() < deadline:
                started = time.perf_counter()
                try:
                    response = await client.get("/api/sensors/")
                    response.raise_for_status()
                    latencies.append((time.perf_counter() - started) * 1000)
                    completed += 1
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    return completed
            return completed

        started = time.perf_counter()
        results = await asyncio.gather(*[worker() for _ in range(concurrency)])
        elapsed = time.perf_counter() - started
    completed = sum(results)
    return {
        "requests": completed,
        "elapsed_seconds": elapsed,
        "qps": completed / elapsed if elapsed else 0.0,
        "latency_p95_ms": percentile(latencies, 0.95),
        "errors": errors[:20],
    }


async def _ws_client(ws_url: str, seconds: float = 5.0) -> dict[str, Any]:
    frames = 0
    latencies: list[float] = []
    deadline = time.monotonic() + seconds
    async with websockets.connect(ws_url, open_timeout=5, close_timeout=2) as socket:
        while time.monotonic() < deadline:
            remaining = max(0.1, deadline - time.monotonic())
            try:
                raw = await asyncio.wait_for(
                    socket.recv(),
                    timeout=min(2.5, remaining),
                )
            except TimeoutError:
                break
            payload = json.loads(raw)
            frames += 1
            timestamps = [
                float(reading["timestamp"])
                for reading in payload.get("sensors", [])
                if isinstance(reading, Mapping) and "timestamp" in reading
            ]
            if timestamps:
                latencies.append(max(0.0, time.time() - max(timestamps)))
    return {"frames": frames, "latencies_seconds": latencies}


async def _websocket_load(
    ws_url: str,
    *,
    clients: int = 10,
    seconds: float = 5.0,
) -> dict[str, Any]:
    results = await asyncio.gather(
        *[_ws_client(ws_url, seconds) for _ in range(clients)],
        return_exceptions=True,
    )
    failures = [str(result) for result in results if isinstance(result, Exception)]
    successful = [result for result in results if isinstance(result, dict)]
    frame_counts = [int(result["frames"]) for result in successful]
    latencies = [
        latency
        for result in successful
        for latency in result["latencies_seconds"]
    ]
    return {
        "requested_clients": clients,
        "connected_clients": len(successful),
        "failures": failures,
        "frames_per_client": frame_counts,
        "minimum_frames": min(frame_counts, default=0),
        "latency_p95_seconds": percentile(latencies, 0.95),
        "latency_p95_ms": percentile(latencies, 0.95) * 1000,
    }


def run_load_benchmark(temporary_root: Path) -> dict[str, Any]:
    config = AppConfig(
        simulation_enabled=True,
        live_interval_seconds=1.0,
        checkpoint_path=temporary_root / "load.json",
        log_level="WARNING",
    )
    with running_server(config) as (base_url, ws_url):
        api_result = asyncio.run(_api_load_workers(base_url))
        websocket_result = asyncio.run(_websocket_load(ws_url))
    gates = [
        create_gate(
            "api_qps",
            api_result["qps"],
            50,
            comparison=">=",
            unit="requests/s",
        ),
        create_gate(
            "websocket_clients",
            websocket_result["connected_clients"],
            10,
            comparison=">=",
            unit="clients",
        ),
        create_gate(
            "websocket_min_frames",
            websocket_result["minimum_frames"],
            4,
            comparison=">=",
            unit="frames/5s",
        ),
        create_gate(
            "websocket_p95_latency_ms",
            websocket_result["latency_p95_ms"],
            500,
            comparison="<=",
            unit="ms",
        ),
    ]
    return {
        "api": api_result,
        "websocket": websocket_result,
        "gates": gates,
    }


def load_validation_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            timestamp = datetime.fromisoformat(row["timestamp"]).timestamp()
            rows.append(
                {
                    "sensor_id": row["sensor_id"],
                    "name": row["name"],
                    "type": row["type"],
                    "value": float(row["value"]),
                    "timestamp": timestamp,
                    "damage_label": int(row["damage_label"]),
                    "damage_event": row.get("damage_event", ""),
                }
            )
    rows.sort(key=lambda item: (item["timestamp"], item["sensor_id"]))
    return rows


def _window_key(timestamp: float) -> int:
    return int(timestamp // 60)


def run_rule_algorithm_acceptance() -> dict[str, Any]:
    manifest = json.loads(VALIDATION_MANIFEST.read_text(encoding="utf-8"))
    dataset_path = ROOT / manifest["path"]
    actual_hash = sha256_file(dataset_path)
    if actual_hash != manifest["sha256"]:
        raise ValueError(
            f"validation dataset checksum mismatch: {actual_hash} != "
            f"{manifest['sha256']}"
        )
    rows = load_validation_rows(dataset_path)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_window_key(row["timestamp"])].append(row)

    configuration = AppConfig(simulation_enabled=False)
    engine = MonitoringEngine(
        thresholds=configuration.thresholds,
        sensor_thresholds=configuration.sensor_thresholds,
    )
    labels: list[bool] = []
    raw_predictions: list[bool] = []
    alert_counts: list[int] = []
    window_events: list[str] = []
    source_counts: Counter[str] = Counter()
    started = time.perf_counter()

    for _, items in sorted(grouped.items()):
        records: list[SensorReadingRecord] = [
            {
                "sensor_id": item["sensor_id"],
                "name": item["name"],
                "type": item["type"],
                "value": item["value"],
                "timestamp": item["timestamp"],
            }
            for item in items
        ]
        batch = SensorBatch(records=records, live_eligibility=LiveEligibility.BACKFILL)
        engine.ingest(batch)
        alerts = engine.check_thresholds(batch)
        alert_counts.append(len(alerts))
        for alert in alerts:
            source_counts[alert.source] += 1
        labels.append(any(item["damage_label"] for item in items))
        raw_predictions.append(bool(alerts))
        events = {item["damage_event"] for item in items if item["damage_event"]}
        window_events.append(next(iter(events), ""))

    lookback = int(manifest["evaluation"]["confirmation_lookback_minutes"])
    minimum_alerts = int(manifest["evaluation"]["confirmation_min_alerts"])
    confirmed_predictions = [
        sum(alert_counts[max(0, index - lookback + 1) : index + 1]) >= minimum_alerts
        for index in range(len(alert_counts))
    ]
    confirmed_metrics = classification_metrics(labels, confirmed_predictions)
    raw_metrics = classification_metrics(labels, raw_predictions)

    event_predictions: dict[str, bool] = defaultdict(bool)
    event_windows: Counter[str] = Counter()
    for index, event in enumerate(window_events):
        if not event:
            continue
        event_windows[event] += 1
        event_predictions[event] = (
            event_predictions[event] or confirmed_predictions[index]
        )
    event_recall = (
        sum(event_predictions.values()) / len(event_windows) if event_windows else 0.0
    )

    elapsed = time.perf_counter() - started
    gates = [
        create_gate(
            "validation_accuracy",
            confirmed_metrics["accuracy"],
            float(manifest["evaluation"]["accuracy_min"]),
            comparison=">=",
            unit="ratio",
        ),
        create_gate(
            "validation_false_positive_rate",
            confirmed_metrics["false_positive_rate"],
            float(manifest["evaluation"]["false_positive_rate_max"]),
            comparison="<=",
            unit="ratio",
        ),
    ]
    return {
        "dataset": manifest,
        "dataset_sha256": actual_hash,
        "runtime_seconds": elapsed,
        "threshold_profile": {
            "thresholds": {
                sensor_type: dict(levels)
                for sensor_type, levels in configuration.thresholds.items()
            },
            "sensor_thresholds": {
                sensor_id: dict(levels)
                for sensor_id, levels in configuration.sensor_thresholds.items()
            },
            "sensor_threshold_types": dict(DEFAULT_SENSOR_THRESHOLD_TYPES),
            "provenance": configuration.threshold_provenance.to_dict(),
        },
        "confirmed_metrics": confirmed_metrics,
        "raw_metrics": raw_metrics,
        "event_recall": event_recall,
        "events": {
            event: {
                "windows": event_windows[event],
                "detected": event_predictions[event],
            }
            for event in event_windows
        },
        "sample_stats": {
            "readings": len(rows),
            "sensors": len({row["sensor_id"] for row in rows}),
            "windows": len(labels),
            "positive_windows": sum(labels),
            "negative_windows": len(labels) - sum(labels),
            "event_count": len(event_windows),
            "alert_source_counts": dict(source_counts),
        },
        "gates": gates,
    }


def run_test_suite() -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    elapsed = time.perf_counter() - started
    output = (completed.stdout + completed.stderr).strip().splitlines()
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "runtime_seconds": elapsed,
        "output_tail": output[-20:],
        "gates": [
            {
                "name": "test_suite",
                "value": completed.returncode,
                "limit": 0,
                "comparison": "==",
                "unit": "exit_code",
                "passed": completed.returncode == 0,
            }
        ],
    }


def environment_info() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for package in ("fastapi", "numpy", "scikit-learn", "uvicorn", "pytest"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    git_commit = _git_output(["rev-parse", "HEAD"]) or "unknown"
    git_status = _git_output(["status", "--porcelain"]) or ""
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "packages": packages,
        "git_commit": git_commit,
        "git_dirty": bool(git_status.strip()),
    }


def _git_output(arguments: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _artifact_payload(
    *,
    test_result: dict[str, Any] | None,
    api_result: dict[str, Any],
    detector_result: dict[str, Any],
    load_result: dict[str, Any],
    algorithm_result: dict[str, Any] | None,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    results = (
        test_result,
        api_result,
        detector_result,
        load_result,
        algorithm_result,
    )
    for result in results:
        if result is None:
            continue
        gates.extend(result.get("gates", []))
    if test_result is None:
        gates.append(
            {
                "name": "test_suite",
                "value": None,
                "limit": 0,
                "comparison": "==",
                "unit": "exit_code",
                "passed": False,
            }
        )
    if algorithm_result is None:
        gates.append(
            {
                "name": "validation_accuracy",
                "value": None,
                "limit": 0.9,
                "comparison": ">=",
                "unit": "ratio",
                "passed": False,
            }
        )
    failed = [gate["name"] for gate in gates if not gate["passed"]]
    threshold_profile = (
        algorithm_result.get("threshold_profile") if algorithm_result else None
    )
    if threshold_profile is None:
        configuration = AppConfig(simulation_enabled=False)
        threshold_profile = {
            "thresholds": configuration.thresholds,
            "sensor_thresholds": configuration.sensor_thresholds,
            "sensor_threshold_types": dict(DEFAULT_SENSOR_THRESHOLD_TYPES),
            "provenance": configuration.threshold_provenance.to_dict(),
        }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "reproduction_command": REPRODUCTION_COMMAND,
        "environment": environment_info(),
        "threshold_profile_version": threshold_profile["provenance"][
            "profile_version"
        ],
        "threshold_profile": threshold_profile,
        "source_identity": {
            "validation_dataset": (
                algorithm_result["dataset_sha256"] if algorithm_result else None
            ),
            "validation_manifest": str(VALIDATION_MANIFEST.relative_to(ROOT)),
        },
        "status": "passed" if not failed else "failed",
        "exit_reason": (
            "all gates passed"
            if not failed
            else "failed gates: " + ", ".join(failed)
        ),
        "gates": gates,
        "tests": test_result,
        "api_performance": api_result,
        "detector_performance": detector_result,
        "load": load_result,
        "algorithm_acceptance": algorithm_result,
    }


def write_artifacts(payload: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "acceptance.json"
    markdown_path = output_dir / "acceptance.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# System Acceptance Report",
        "",
        f"- Status: **{payload['status']}**",
        f"- Generated: {payload['generated_at']}",
        f"- Exit reason: {payload['exit_reason']}",
        f"- Reproduction: `{payload['reproduction_command']}`",
        f"- Git commit: `{payload['environment']['git_commit']}`",
        f"- Python: `{payload['environment']['python'].splitlines()[0]}`",
        "",
    ]
    profile = payload.get("threshold_profile")
    if isinstance(profile, Mapping):
        provenance = profile.get("provenance", {})
        lines.extend(
            [
                "## Threshold Profile",
                "",
                f"- Version: `{provenance.get('profile_version')}`",
                f"- Status: `{provenance.get('status')}`",
                "",
                "| Measurement | Type | Yellow | Orange | Red |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        sensor_types = profile.get("sensor_threshold_types", {})
        for sensor_id, levels in sorted(profile.get("sensor_thresholds", {}).items()):
            lines.append(
                f"| {sensor_id} | {sensor_types.get(sensor_id, 'override')} "
                f"| {levels['yellow']} | {levels['orange']} | {levels['red']} |"
            )
        for sensor_type, levels in sorted(profile.get("thresholds", {}).items()):
            lines.append(
                f"| type fallback | {sensor_type} "
                f"| {levels['yellow']} | {levels['orange']} | {levels['red']} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Gates",
            "",
            "| Gate | Value | Limit | Result |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for gate in payload["gates"]:
        lines.append(
            f"| {gate['name']} | {gate['value']} | {gate['limit']} "
            f"({gate['comparison']}) | {'PASS' if gate['passed'] else 'FAIL'} |"
        )
    algorithm = payload.get("algorithm_acceptance")
    if algorithm is not None:
        metrics = algorithm["confirmed_metrics"]
        lines.extend(
            [
                "",
                "## Validation Dataset",
                "",
                f"- Dataset: `{algorithm['dataset']['path']}`",
                f"- SHA-256: `{algorithm['dataset_sha256']}`",
                f"- Source kind: `{algorithm['dataset']['source_kind']}`",
                f"- Confirmed accuracy: {metrics['accuracy']:.4f}",
                (
                    "- Confirmed false-positive rate: "
                    f"{metrics['false_positive_rate']:.4f}"
                ),
                f"- Recall: {metrics['recall']:.4f}",
                f"- Event recall: {algorithm['event_recall']:.4f}",
                (
                    "- Raw rule accuracy (without confirmation): "
                    f"{algorithm['raw_metrics']['accuracy']:.4f}"
                ),
                "",
                (
                    "Synthetic data validates behavior and reproducibility only. "
                    "Real bridge accuracy requires calibrated field data."
                ),
            ]
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-performance", action="store_true")
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--skip-algorithm", action="store_true")
    args = parser.parse_args(argv)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or DEFAULT_RUNS_DIR / timestamp
    with tempfile.TemporaryDirectory(prefix="bridge-acceptance-") as temporary:
        temporary_root = Path(temporary)
        test_result = None if args.skip_tests else run_test_suite()
        api_result = (
            {"gates": []}
            if args.skip_performance
            else run_api_performance(temporary_root)
        )
        detector_result = (
            {"gates": []}
            if args.skip_performance
            else run_detector_performance()
        )
        load_result = (
            {"gates": []} if args.skip_load else run_load_benchmark(temporary_root)
        )
        algorithm_result = (
            None if args.skip_algorithm else run_rule_algorithm_acceptance()
        )

    payload = _artifact_payload(
        test_result=test_result,
        api_result=api_result,
        detector_result=detector_result,
        load_result=load_result,
        algorithm_result=algorithm_result,
    )
    json_path, markdown_path = write_artifacts(payload, output_dir)
    print(f"Acceptance status: {payload['status']}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
