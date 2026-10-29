---
status: accepted
---

# VBA Recording-Level Benchmark

The `VBA` variable in `Old_ADA_Bridge-damage_vibration_data.mat` is the acceptance benchmark for dataset-driven detector quality. Evaluation is recording-level because damage labels exist only per Vibration Recording and one-second readings are highly correlated; reading-level scoring would inflate the sample count and invent sensor-level ground truth. The benchmark keeps the raw 58.8 MB source external, evaluates deterministic five-fold case-stratified folds from the derived CSV through the production service seam, and accepts only accuracy of at least 90% with a false-positive rate of at most 10%.

The operational protocol is `benchmarks/vba/README.md`; the machine-readable contract is `benchmarks/vba/manifest.json`.

## Consequences

- The raw source must be supplied externally and validated by SHA-256 before conversion.
- `RCV` contributes to the aggregate negative class but its false-positive rate is reported separately.
- Reading-level and per-sensor results remain diagnostic and do not override recording-level acceptance.
- Every declared detector component must be present and every baseline ready; `--allow-partial` cannot produce an acceptance pass.
- Adding or replacing a benchmarked detector requires benchmark-side state restoration support.
