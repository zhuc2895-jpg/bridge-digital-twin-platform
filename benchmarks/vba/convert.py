"""Convert the VBA MATLAB cell array into normalized benchmark readings."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.io import loadmat

BENCHMARK_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = BENCHMARK_DIR / "manifest.json"
DEFAULT_OUTPUT_PATH = BENCHMARK_DIR / "normalized.csv"


def convert_recording(
    record: np.ndarray,
    *,
    vibration_case: str,
    repetition: int,
    recording_start_epoch: float,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Convert one multichannel VBA recording into scalar RMS readings."""
    conversion = manifest["conversion"]
    time_column = _time_column_index(conversion)
    signal_columns = [
        int(column) - 1 for column in conversion["signal_columns_one_based"]
    ]
    required_columns = max([time_column, *signal_columns]) + 1
    if record.ndim != 2 or record.shape[1] < required_columns:
        raise ValueError(
            f"VBA recording must be a two-dimensional N by {required_columns} array"
        )
    if conversion["aggregation"] != "rms":
        raise ValueError(f"Unsupported VBA aggregation: {conversion['aggregation']}")
    if conversion["partial_bucket_policy"] != "discard":
        raise ValueError(
            "Unsupported partial bucket policy: "
            f"{conversion['partial_bucket_policy']}"
        )

    times = np.asarray(record[:, time_column], dtype=float)
    if times.size < 2 or not np.all(np.isfinite(times)):
        raise ValueError("VBA recording must contain a finite time axis")
    deltas = np.diff(times)
    if np.any(deltas <= 0) or not np.allclose(deltas, np.median(deltas)):
        raise ValueError("VBA time axis must be strictly regular and increasing")

    bucket_seconds = float(conversion["bucket_seconds"])
    readings_per_bucket = int(round(bucket_seconds / float(np.median(deltas))))
    if readings_per_bucket <= 1:
        raise ValueError("VBA sampling rate is too low for the configured buckets")

    signals = np.asarray(record[:, signal_columns], dtype=float)
    if not np.all(np.isfinite(signals)):
        raise ValueError("VBA signal channels must be finite")

    condition = _structural_condition(vibration_case)
    damage_labels = manifest["corpus"]["damage_labels"]
    if condition not in damage_labels:
        raise ValueError(f"Unknown VBA structural condition: {condition}")
    damage_label = int(damage_labels[condition])
    case_slug = re.sub(r"[^A-Za-z0-9]+", "_", vibration_case).strip("_")
    recording_id = f"{case_slug}_{repetition:02d}"
    start_time = float(times[0])
    row_count = times.size // readings_per_bucket
    unit_factor = float(conversion["unit_factor"])
    rows: list[dict[str, Any]] = []

    for bucket_index in range(row_count):
        bucket_slice = slice(
            bucket_index * readings_per_bucket,
            (bucket_index + 1) * readings_per_bucket,
        )
        rms = np.sqrt(np.mean(np.square(signals[bucket_slice]), axis=0))
        relative_time = start_time + (bucket_index + 1) * bucket_seconds
        timestamp = recording_start_epoch + relative_time - start_time
        for channel_index, signal_column in enumerate(
            conversion["signal_columns_one_based"]
        ):
            rows.append(
                {
                    "recording_id": recording_id,
                    "vibration_case": vibration_case,
                    "repetition": repetition,
                    "sensor_id": conversion["sensor_ids"][str(signal_column)],
                    "sensor_name": f"VBA No{int(signal_column) - 1}",
                    "sensor_type": "acceleration",
                    "timestamp": timestamp,
                    "relative_time_seconds": relative_time,
                    "value": float(rms[channel_index] * unit_factor),
                    "damage_label": damage_label,
                }
            )
    return rows


def convert_mat_file(
    mat_path: Path,
    *,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate and convert every non-empty VBA recording in the source file."""
    verify_source_mat(mat_path, manifest)
    source = loadmat(mat_path, variable_names=[manifest["source"]["matlab_variable"]])
    vba = source[manifest["source"]["matlab_variable"]]
    rows: list[dict[str, Any]] = []
    condition_counts = {
        condition: 0 for condition in manifest["corpus"]["structural_condition_counts"]
    }
    vibration_case_counts = {
        vibration_case: 0
        for vibration_case in manifest["corpus"]["vibration_case_counts"]
    }
    recording_total = 0
    time_column = _time_column_index(manifest["conversion"])
    session_start = (
        datetime.fromisoformat(
            manifest["conversion"]["utc_start"].replace("Z", "+00:00")
        )
        .astimezone(timezone.utc)
        .timestamp()
    )

    for case_row in range(1, vba.shape[0]):
        vibration_case = str(vba[case_row, 0].item())
        condition = _structural_condition(vibration_case)
        if condition not in condition_counts:
            raise ValueError(f"Unknown VBA structural condition: {condition}")
        if vibration_case not in vibration_case_counts:
            raise ValueError(f"Unknown VBA vibration case: {vibration_case}")
        repetition = 0
        for column in range(1, vba.shape[1]):
            cell = vba[case_row, column]
            if not isinstance(cell, np.ndarray) or cell.size == 0:
                continue
            repetition += 1
            recording_total += 1
            condition_counts[condition] += 1
            vibration_case_counts[vibration_case] += 1
            record = np.asarray(cell, dtype=float)
            converted = convert_recording(
                record,
                vibration_case=vibration_case,
                repetition=repetition,
                recording_start_epoch=session_start,
                manifest=manifest,
            )
            rows.extend(converted)
            duration = float(record[-1, time_column] - record[0, time_column])
            session_start += duration + manifest["conversion"]["recording_gap_seconds"]

    expected_total = manifest["corpus"]["recording_count"]
    if recording_total != expected_total:
        raise ValueError(
            f"VBA recording count mismatch: {recording_total} != {expected_total}"
        )
    if condition_counts != manifest["corpus"]["structural_condition_counts"]:
        raise ValueError(f"VBA structural condition count mismatch: {condition_counts}")
    if vibration_case_counts != manifest["corpus"]["vibration_case_counts"]:
        raise ValueError(f"VBA vibration case count mismatch: {vibration_case_counts}")
    return rows


def write_csv(
    rows: Iterable[dict[str, Any]],
    output_path: Path,
    manifest: Mapping[str, Any],
) -> int:
    """Write normalized readings using the manifest CSV contract."""
    fieldnames = list(manifest["normalized_csv"]["columns"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def _time_column_index(conversion: Mapping[str, Any]) -> int:
    return int(conversion["time_column_one_based"]) - 1


def _structural_condition(vibration_case: str) -> str:
    return vibration_case.split()[0]


def verify_source_mat(path: Path, manifest: Mapping[str, Any]) -> None:
    """Verify the raw MAT source against the benchmark manifest."""
    _verify_sha256(
        path,
        manifest["source"]["sha256"],
        label="VBA source",
    )


def verify_normalized_csv(path: Path, manifest: Mapping[str, Any]) -> None:
    """Verify the committed normalized CSV against the benchmark manifest."""
    _verify_sha256(
        path,
        manifest["normalized_csv"]["sha256"],
        label="normalized CSV",
    )


def _verify_sha256(path: Path, expected: str, *, label: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest().upper()
    if actual != expected.upper():
        raise ValueError(f"{label} checksum mismatch: {actual} != {expected}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mat-path", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows = convert_mat_file(args.mat_path, manifest=manifest)
    count = write_csv(rows, args.output, manifest)
    verify_normalized_csv(args.output, manifest)
    print(f"Wrote {count} normalized readings to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
