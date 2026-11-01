# VBA Fusion Acceptance

- Mode: enhanced
- Status: **passed**
- Generated: 2026-11-01T13:04:41.780542+00:00
- Reproduction: `python -m benchmarks.vba.evaluate --mode enhanced`
- Git commit: `bfefb1199f850a3d2f3b2efa276c58193416e85d`
- Dataset SHA-256: `BE13A4CAE46E877C6613FABA9ABF164449CFC58EAA73AC86599473EF078FF7A3`

## Overall Metrics

- Accuracy: 0.9706
- False-positive rate: 0.0278
- Recall: 0.9688
- Precision: 0.9688
- F1: 0.9688
- Confusion matrix: {'tp': 31, 'tn': 35, 'fp': 1, 'fn': 1}

## Gates

| Gate | Value | Limit | Result |
| --- | ---: | ---: | --- |
| vba_accuracy | 0.9705882352941176 | 0.9 | PASS |
| vba_false_positive_rate | 0.027777777777777776 | 0.1 | PASS |
| single_chain_p95_ms | 6.741237499227282 | 200.0 | PASS |
| all_components_present | 6 | 6 | PASS |
| all_baselines_ready | 1 | 1 | PASS |
| fusion_component_checks | 1 | 1 | PASS |
| false_positive_rate_not_above_baseline | 0.027777777777777776 | 1.0 | PASS |
| recall_not_unexplained_drop | 0.96875 | 0.95 | PASS |

## Calibration

| Bin | Recordings | FPR | Recall |
| --- | ---: | ---: | ---: |
| low_cognition | 60 | 1.0000 | 1.0000 |
| high_uncertainty | 60 | 1.0000 | 1.0000 |
| isolated_spatial | 3 | n/a | 1.0000 |
| coherent_spatial | 49 | 1.0000 | 1.0000 |

Synthetic compensation reliability (synthetic fixtures, not real VBA structural-response accuracy)

| Reliability | Samples | MAE |
| --- | ---: | ---: |
| high | 26 | 12.082 |
| medium | 21 | 22.542 |
| low | 1 | 48.718 |

## Traceability

- Gated AI alerts: 358
- Isolated spatial suppressions: 0
- Detector failures: 0
- Processing p95: 6.741 ms

synthetic fixtures, not real VBA structural-response accuracy
