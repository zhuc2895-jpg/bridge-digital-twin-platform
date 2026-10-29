"""Convert the VBA MATLAB cell array into normalized benchmark readings."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

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
) -> list[dict[str, Any]]:
    """Convert one multichannel VBA recording into scalar RMS readings."""
    if record.ndim != 2 or record.shape[1] < 12:
        raise ValueError("VBA recording must be a two-dimensional N by 12 array")

    times = np.asarray(record[:, 0], dtype=float)
    if times.size < 2 or not np.all(np.isfinite(times)):
        raise ValueError("VBA recording must contain a finite time axis")
    deltas = np.diff(times)
    if np.any(deltas <= 0) or not np.allclose(deltas, np.median(deltas)):
        raise ValueError("VBA time axis must be strictly regular and increasing")

    readings_per_bucket = int(round(1.0 / float(np.median(deltas))))
    if readings_per_bucket <= 1:
        raise ValueError("VBA sampling rate is too low for one-second buckets")

    signal_columns = list(range(1, 9))
    signals = np.asarray(record[:, signal_columns], dtype=float)
    if not np.all(np.isfinite(signals)):
        raise ValueError("VBA signal channels must be finite")

    condition = vibration_case.split()[0]
    damage_label = 0 if condition in {"INT", "RCV"} else 1
    case_slug = re.sub(r"[^A-Za-z0-9]+", "_", vibration_case).strip("_")
    recording_id = f"{case_slug}_{repetition:02d}"
    start_time = float(times[0])
    row_count = times.size // readings_per_bucket
    rows: list[dict[str, Any]] = []

    for bucket_index in range(row_count):
        bucket_slice = slice(
            bucket_index * readings_per_bucket,
            (bucket_index + 1) * readings_per_bucket,
        )
        rms = np.sqrt(np.mean(np.square(signals[bucket_slice]), axis=0))
        relative_time = start_time + bucket_index + 1.0
        for channel_index, sensor_number in enumerate(range(1, 9)):
            rows.append(
                {
                    "recording_id": recording_id,
                    "vibration_case": vibration_case,
                    "repetition": repetition,
                    "sensor_id": f"S{sensor_number:02d}",
                    "sensor_name": f"VBA No{sensor_number}",
                    "sensor_type": "acceleration",
                    "timestamp": recording_start_epoch + relative_time,
                    "relative_time_seconds": relative_time,
                    "value": float(rms[channel_index] * 9.80665),
                    "damage_label": damage_label,
                }
            )
    return rows


def convert_mat_file(
    mat_path: Path,
    *,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate and convert every non-empty VBA recording in the source file."""
    _verify_sha256(mat_path, manifest["source"]["sha256"])
    source = loadmat(mat_path, variable_names=[manifest["source"]["matlab_variable"]])
    vba = source[manifest["source"]["matlab_variable"]]
    rows: list[dict[str, Any]] = []
    counts = {case: 0 for case in manifest["corpus"]["case_counts"]}
    recording_total = 0
    session_start = (
        datetime.fromisoformat(
            manifest["conversion"]["utc_start"].replace("Z", "+00:00")
        )
        .astimezone(timezone.utc)
        .timestamp()
    )

    for case_row in range(1, vba.shape[0]):
        vibration_case = str(vba[case_row, 0].item())
        condition = vibration_case.split()[0]
        if condition not in counts:
            raise ValueError(f"Unknown VBA condition: {vibration_case}")
        repetition = 0
        for column in range(1, vba.shape[1]):
            cell = vba[case_row, column]
            if not isinstance(cell, np.ndarray) or cell.size == 0:
                continue
            repetition += 1
            recording_total += 1
            counts[condition] += 1
            record = np.asarray(cell, dtype=float)
            converted = convert_recording(
                record,
                vibration_case=vibration_case,
                repetition=repetition,
                recording_start_epoch=session_start,
            )
            rows.extend(converted)
            duration = float(record[-1, 0] - record[0, 0])
            session_start += duration + manifest["conversion"]["recording_gap_seconds"]

    expected_total = manifest["corpus"]["recording_count"]
    if recording_total != expected_total:
        raise ValueError(
            f"VBA recording count mismatch: {recording_total} != {expected_total}"
        )
    if counts != manifest["corpus"]["case_counts"]:
        raise ValueError(f"VBA case count mismatch: {counts}")
    return rows


def write_csv(rows: Iterable[dict[str, Any]], output_path: Path) -> int:
    """Write normalized readings using the benchmark CSV contract."""
    fieldnames = [
        "recording_id",
        "vibration_case",
        "repetition",
        "sensor_id",
        "sensor_name",
        "sensor_type",
        "timestamp",
        "relative_time_seconds",
        "value",
        "damage_label",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def _verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest().upper()
    if actual != expected.upper():
        raise ValueError(f"VBA source checksum mismatch: {actual} != {expected}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mat-path", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows = convert_mat_file(args.mat_path, manifest=manifest)
    count = write_csv(rows, args.output)
    print(f"Wrote {count} normalized readings to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
