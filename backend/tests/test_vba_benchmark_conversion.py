import csv
from pathlib import Path

import numpy as np
import pytest

from benchmarks.vba.convert import convert_recording


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
    )

    assert len(rows) == 16
    assert {row["sensor_id"] for row in rows} == {
        f"S{index:02d}" for index in range(1, 9)
    }
    assert {row["sensor_type"] for row in rows} == {"acceleration"}
    assert {row["damage_label"] for row in rows} == {0}
    assert {row["relative_time_seconds"] for row in rows} == {-4.0, -3.0}
    assert all(row["value"] == pytest.approx(9.80665) for row in rows)
    assert all(
        row["timestamp"] - row["relative_time_seconds"] == 1_617_753_600.0
        for row in rows
    )


NORMALIZED_CSV_PATH = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "vba" / "normalized.csv"
)


def test_committed_normalized_csv_matches_the_benchmark_contract():
    with NORMALIZED_CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 24_552
    assert list(rows[0]) == [
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
    assert {row["sensor_id"] for row in rows} == {
        f"S{index:02d}" for index in range(1, 9)
    }
    assert {row["sensor_type"] for row in rows} == {"acceleration"}
    assert len({row["recording_id"] for row in rows}) == 68

    cases_by_recording = {
        row["recording_id"]: row["vibration_case"].split()[0] for row in rows
    }
    assert {
        case: list(cases_by_recording.values()).count(case)
        for case in {"INT", "RCV", "DMG1", "DMG2", "DMG3"}
    } == {
        "INT": 26,
        "RCV": 10,
        "DMG1": 12,
        "DMG2": 10,
        "DMG3": 10,
    }
