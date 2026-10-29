import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.io import savemat

from benchmarks.vba.convert import (
    convert_mat_file,
    convert_recording,
    verify_normalized_csv,
)


def test_convert_recording_emits_full_bucket_rms_readings():
    time = np.arange(-5.0, -2.5, 0.005)
    record = np.zeros((time.size, 12), dtype=float)
    record[:, 0] = time
    record[:, 1:9] = 1.0
    record[:, 9:12] = 99.0

    rows = convert_recording(
        record,
        vibration_case="INT 40km",
        repetition=1,
        recording_start_epoch=1_617_753_600.0,
        manifest=MANIFEST,
    )

    assert len(rows) == 16
    assert {row["sensor_id"] for row in rows} == {
        f"S{index:02d}" for index in range(1, 9)
    }
    assert {row["sensor_type"] for row in rows} == {"acceleration"}
    assert {row["damage_label"] for row in rows} == {0}
    assert {row["relative_time_seconds"] for row in rows} == {-4.0, -3.0}
    assert all(row["value"] == pytest.approx(9.80665) for row in rows)
    timestamps_by_relative_time = {
        row["relative_time_seconds"]: row["timestamp"] for row in rows
    }
    assert timestamps_by_relative_time == {
        -4.0: 1_617_753_601.0,
        -3.0: 1_617_753_602.0,
    }


BENCHMARK_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "vba"
MANIFEST_PATH = BENCHMARK_DIR / "manifest.json"
NORMALIZED_CSV_PATH = BENCHMARK_DIR / "normalized.csv"
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_committed_normalized_csv_matches_the_benchmark_contract():
    with NORMALIZED_CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 24_552
    assert list(rows[0]) == MANIFEST["normalized_csv"]["columns"]
    assert {row["sensor_id"] for row in rows} == {
        f"S{index:02d}" for index in range(1, 9)
    }
    assert {row["sensor_type"] for row in rows} == {"acceleration"}
    assert len({row["recording_id"] for row in rows}) == 68
    utc_start = (
        datetime.fromisoformat(
            MANIFEST["conversion"]["utc_start"].replace("Z", "+00:00")
        )
        .astimezone(timezone.utc)
        .timestamp()
    )
    assert min(float(row["timestamp"]) for row in rows) >= utc_start

    conditions_by_recording = {
        row["recording_id"]: row["vibration_case"].split()[0] for row in rows
    }
    assert {
        condition: list(conditions_by_recording.values()).count(condition)
        for condition in {"INT", "RCV", "DMG1", "DMG2", "DMG3"}
    } == MANIFEST["corpus"]["structural_condition_counts"]


def test_normalized_csv_verifier_rejects_a_manifest_hash_mismatch(tmp_path):
    csv_path = tmp_path / "normalized.csv"
    csv_path.write_bytes(b"normalized readings")
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest().upper()
    manifest = {"normalized_csv": {"sha256": digest}}

    verify_normalized_csv(csv_path, manifest)

    manifest["normalized_csv"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="normalized CSV checksum mismatch"):
        verify_normalized_csv(csv_path, manifest)


def test_committed_normalized_csv_matches_its_manifest_checksum():
    verify_normalized_csv(NORMALIZED_CSV_PATH, MANIFEST)


def test_convert_mat_file_uses_configured_time_column_for_session_gaps(tmp_path):
    def recording(duration_seconds):
        time = np.arange(-5.0, -5.0 + duration_seconds, 0.005)
        record = np.zeros((time.size, 4), dtype=float)
        record[:, 0] = 999.0
        record[:, 1] = time
        record[:, 2:4] = 1.0
        return record

    first = recording(2.5)
    second = recording(3.5)
    vba = np.empty((2, 3), dtype=object)
    vba[0, :] = ["Case", "No1", "No2"]
    vba[1, 0] = "INT 40km"
    vba[1, 1] = first
    vba[1, 2] = second
    mat_path = tmp_path / "vba.mat"
    savemat(mat_path, {"VBA": vba})

    manifest = json.loads(json.dumps(MANIFEST))
    manifest["source"]["file_name"] = mat_path.name
    manifest["source"]["sha256"] = (
        hashlib.sha256(mat_path.read_bytes()).hexdigest().upper()
    )
    manifest["corpus"]["recording_count"] = 2
    manifest["corpus"]["structural_condition_counts"] = {"INT": 2}
    manifest["corpus"]["vibration_case_counts"] = {"INT 40km": 2}
    manifest["corpus"]["damage_labels"] = {"INT": 0}
    manifest["conversion"]["time_column_one_based"] = 2
    manifest["conversion"]["signal_columns_one_based"] = [3, 4]
    manifest["conversion"]["sensor_ids"] = {"3": "S01", "4": "S02"}

    rows = convert_mat_file(mat_path, manifest=manifest)
    first_timestamps = {}
    for row in rows:
        first_timestamps.setdefault(row["recording_id"], row["timestamp"])
    expected_gap = (first[-1, 1] - first[0, 1]) + 60.0
    assert first_timestamps["INT_40km_02"] - first_timestamps[
        "INT_40km_01"
    ] == pytest.approx(expected_gap)
