# VBA Fusion Acceptance

- Mode: enhanced
- Status: **passed**
- Generated: 2026-11-01T07:13:09.556361+00:00
- Reproduction: `python -m benchmarks.vba.evaluate --mode enhanced`
- Git commit: `16fad09a31f8b16b4ab8cf047cdc309608ad91ce`
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
| single_chain_p95_ms | 10.434187500322878 | 200.0 | PASS |
| all_components_present | 6 | 6 | PASS |
| all_baselines_ready | 1 | 1 | PASS |
| fusion_component_checks | 1 | 1 | PASS |
| false_positive_rate_not_above_baseline | 0.027777777777777776 | 1.0 | PASS |
| recall_not_unexplained_drop | 0.96875 | 0.95 | PASS |

## Traceability

- Gated AI alerts: 24
- Isolated spatial suppressions: 0
- Detector failures: 0
- Processing p95: 10.434 ms

synthetic fixtures, not real VBA structural-response accuracy
