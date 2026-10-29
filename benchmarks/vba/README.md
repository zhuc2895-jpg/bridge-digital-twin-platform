# VBA Recording-Level Benchmark

This document defines the operational protocol for the VBA acceptance benchmark. The machine-readable contract is `benchmarks/vba/manifest.json`.

## Source and integrity

The source is the external `Old_ADA_Bridge-damage_vibration_data.mat` file, using its `VBA` variable. The raw file is not committed. Every run validates the source SHA-256:

`001F8A1ADD06649A6156FA7D33440D889A9E0CB036C17895E9F357BD1E281DA5`

The normalized derived CSV is committed at `benchmarks/vba/normalized.csv` so acceptance runs do not depend on the source file path after conversion. Regenerate it with:

```powershell
python -m benchmarks.vba.convert --mat-path <path-to-mat-file>
```

## Corpus and ground truth

The VBA corpus contains 68 recordings:

- 26 `INT` recordings
- 10 `RCV` recordings
- 12 `DMG1` recordings
- 10 `DMG2` recordings
- 10 `DMG3` recordings

`INT` and `RCV` have damage label `0`. `DMG1`, `DMG2`, and `DMG3` have damage label `1`.

Columns 10, 11, and 12 are operational event markers. They are not damage labels and must not affect ground truth.

## Conversion

Columns 2 through 9 are eight stable acceleration channels mapped to `S01` through `S08`. Values are acceleration in `g` and are multiplied by `9.80665` to produce `m/s^2`.

Each channel is reduced to one-second RMS readings emitted at the end of the bucket. Partial buckets are discarded. Synthetic UTC sessions begin at `2021-04-07T00:00:00Z`, preserve relative recording time, and use 60-second gaps between recordings.

The normalized CSV columns are:

`recording_id`, `vibration_case`, `repetition`, `sensor_id`, `sensor_name`, `sensor_type`, `timestamp`, `relative_time_seconds`, `value`, `damage_label`.

## Evaluation protocol

Use five recording-level folds stratified by vibration case with random seed `42`. Every recording belongs to exactly one test fold.

For each fold, learn and update sensor baselines using all out-of-fold `INT` recordings while ignoring their outputs. `RCV` and `DMG` recordings never train a baseline. Evaluate every held-out recording from an independent restored copy of the post-baseline detector state. Snapshot/restore is benchmark-only infrastructure; it does not extend the production detector contract.

The primary result uses the production service seam, current runtime threshold profiles, and the full rule + AI + voting + arbitration pipeline. A held-out recording is detected when any sensor produces any retained alert from any source at any level during that recording.

The full pipeline uses the runtime ten-second alert cooldown. Individual component diagnostics use raw per-reading verdicts without cooldown.

## Metrics and acceptance

Primary classification is pooled over all out-of-fold recordings. Report:

- Accuracy
- False-positive rate
- Recall
- Precision
- F1
- Confusion matrix
- Per-case metrics
- Per-fold metrics
- Per-sensor alert counts
- Alert-source counts
- Alert-level counts

`INT` and `RCV` aggregate as negatives, but each has a separately reported false-positive rate.

Acceptance requires accuracy of at least `0.90`, false-positive rate of at most `0.10`, a valid checksum, all declared components present, and every baseline ready. A missing prerequisite fails the run.

Runs always write JSON and Markdown artifacts containing environment metadata, source checksum, fold assignments, metrics, and the exit reason. The acceptance command exits zero only when all gates pass. `--allow-partial` is diagnostic-only and cannot produce an acceptance pass.
