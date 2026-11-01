# VBA Recording-Level Benchmark

This document defines the operational protocol for the VBA acceptance benchmark. The machine-readable contract is `benchmarks/vba/manifest.json`.

## Source and checksum stages

The source is the external `data/external/Old_ADA_Bridge-damage_vibration_data.mat` file, using its `VBA` variable. The raw file is not committed. Conversion validates the source SHA-256:

`001F8A1ADD06649A6156FA7D33440D889A9E0CB036C17895E9F357BD1E281DA5`

The normalized derived CSV is committed at `benchmarks/vba/normalized.csv`. Evaluation validates this CSV against the manifest SHA-256, so acceptance runs do not need the MAT file. Reports record both hashes.

Install benchmark dependencies and regenerate the CSV with:

```powershell
python -m pip install -r benchmarks/vba/requirements.txt
python -m benchmarks.vba.convert --mat-path <path-to-mat-file>
```

The command fails unless the MAT source hash matches and the generated CSV hash matches the manifest.

## Corpus and ground truth

The VBA corpus contains 68 recordings. Structural-condition counts are:

- 26 `INT` recordings
- 10 `RCV` recordings
- 12 `DMG1` recordings
- 10 `DMG2` recordings
- 10 `DMG3` recordings

The complete Vibration Case counts are:

- `INT 30km`: 11
- `INT 50km`: 5
- `INT 40km`: 10
- `DMG1 40km`: 12
- `DMG2 40km`: 10
- `RCV 40km`: 10
- `DMG3 40km`: 10

`INT` and `RCV` have damage label `0`. `DMG1`, `DMG2`, and `DMG3` have damage label `1`.

Columns 10, 11, and 12 are operational event markers. They are not damage labels and must not affect ground truth.

## Conversion

Columns are one-based in the manifest. Columns 2 through 9 are eight stable acceleration channels mapped to `S01` through `S08`. Values are acceleration in `g` and are multiplied by `9.80665` to produce `m/s^2`.

Each channel is reduced to one-second RMS readings emitted at bucket end. Partial buckets are discarded. The `utc_start` value corresponds to source relative time `-5.0` seconds; the first emitted bucket-end timestamp is one second after `utc_start`. Synthetic sessions use 60-second gaps between recordings.

The normalized CSV columns are defined by `manifest.json.normalized_csv.columns`.

## Evaluation protocol

Use `StratifiedKFold` over recording IDs, stratified by `vibration_case`, with `n_splits=5`, `shuffle=true`, and `random_state=42`. Every Vibration Recording belongs to exactly one test fold.

For each fold, learn and update sensor baselines using all out-of-fold `INT` recordings while ignoring their outputs. `RCV` and `DMG` recordings never train a baseline. Feed baseline and evaluation readings in ascending `timestamp`, then `sensor_id` order.

Each held-out recording starts from an independent restored copy of the post-baseline state. The snapshot is captured only after all baseline readings are processed and pending refits complete. It includes baseline learners, EMA state, rolling windows, fitted Isolation Forest models, score calibration, GAN-AE distribution state, and voting configuration.

Per-recording state resets cover the engine latest snapshot, engine history, retained alerts, alert cooldowns, detector failure counters, detector detection counters, and pending refit jobs. This prevents one recording from affecting the next.

The primary result uses the production service seam, current runtime threshold profiles, and the full rule + AI + voting + arbitration pipeline. All declared components must exist:

- `rule`
- `ai_stalwart`
- `ai_gan_ae`
- `ai_isolation_forest`
- `ai_dual_confirm`
- `ai_feature_arbitration`

All baselines for `S01` through `S08` must be ready.

A held-out recording is detected when any required sensor produces any retained alert from any source at any level during that recording. The full pipeline uses the runtime ten-second cooldown. Individual component diagnostics use raw per-reading verdicts without cooldown.

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

Acceptance requires accuracy of at least `0.90`, false-positive rate of at most `0.10`, valid checksums, all declared components present, and every baseline ready. A missing prerequisite fails the run.

Runs always write JSON and Markdown artifacts containing environment, code version, threshold-profile version, source identity, both dataset hashes, reproduction command, fold assignments, sample counts, metrics, and exit reason. The acceptance command exits zero only when all gates pass. `--allow-partial` is diagnostic-only and cannot produce an acceptance pass.

## Frozen baseline and fusion-enhanced acceptance

The pre-enhancement alert-pipeline result is frozen in `baseline-v1.json`. It records the code version, dataset hash, any-alert recording metrics, per-fold/per-case results, component checks, latency, memory, and exit reason.

The enhanced run is produced with:

```powershell
python -m benchmarks.vba.evaluate --mode enhanced
```

It reports the raw alert-pipeline metrics beside the fusion predictions so suppression is visible rather than hidden. The fusion model is a standardized logistic classifier over resampled multichannel recording sequences, trained only on out-of-fold recording labels. Cognition, uncertainty, spatial residual, gated-alert counts, isolated-suppression counts, detector failures, and synthetic compensation/modal checks are reported in the same artifact for traceability and calibration analysis.

Synthetic compensation and modal-inversion checks validate behavior and contracts only. They are never presented as real VBA structural-response accuracy.
