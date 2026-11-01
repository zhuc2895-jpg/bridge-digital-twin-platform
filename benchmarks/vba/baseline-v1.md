# VBA Fusion Acceptance

- Mode: baseline
- Status: **failed**
- Generated: 2026-11-01T12:45:01.297142+00:00
- Reproduction: `python -m benchmarks.vba.evaluate --mode baseline --output benchmarks/vba/baseline-v1.json`
- Git commit: `c00ea96d05f99719009553300a2dffdc6c585c11`
- Dataset SHA-256: `BE13A4CAE46E877C6613FABA9ABF164449CFC58EAA73AC86599473EF078FF7A3`

## Overall Metrics

- Accuracy: 0.4706
- False-positive rate: 1.0000
- Recall: 1.0000
- Precision: 0.4706
- F1: 0.6400
- Confusion matrix: {'tp': 32, 'tn': 0, 'fp': 36, 'fn': 0}

## Gates

| Gate | Value | Limit | Result |
| --- | ---: | ---: | --- |
| vba_accuracy | 0.47058823529411764 | 0.9 | FAIL |
| vba_false_positive_rate | 1.0 | 0.1 | FAIL |
| single_chain_p95_ms | 9.434699999474105 | 200.0 | PASS |
| all_components_present | 6 | 6 | PASS |
| all_baselines_ready | 1 | 1 | PASS |
| fusion_component_checks | 1 | 1 | PASS |

## Calibration

| Bin | Recordings | FPR | Recall |
| --- | ---: | ---: | ---: |
| low_cognition | 61 | 1.0000 | 1.0000 |
| high_uncertainty | 61 | 1.0000 | 1.0000 |
| isolated_spatial | 0 | n/a | 0.0000 |
| coherent_spatial | 0 | n/a | 0.0000 |

Synthetic compensation reliability (synthetic fixtures, not real VBA structural-response accuracy)

| Reliability | Samples | MAE |
| --- | ---: | ---: |
| high | 26 | 12.082 |
| medium | 21 | 22.542 |
| low | 1 | 48.718 |

## Traceability

- Gated AI alerts: 0
- Isolated spatial suppressions: 0
- Detector failures: 0
- Processing p95: 9.435 ms

synthetic fixtures, not real VBA structural-response accuracy
