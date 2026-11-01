# VBA Fusion Acceptance

- Mode: enhanced
- Status: **passed**
- Generated: 2026-11-01T07:34:32.751368+00:00
- Reproduction: `python -m benchmarks.vba.evaluate --mode enhanced`
- Git commit: `60308e0fc53054a652750021381a264fb66d9b65`
- Dataset SHA-256: `BE13A4CAE46E877C6613FABA9ABF164449CFC58EAA73AC86599473EF078FF7A3`

## Overall Metrics

- Accuracy: 0.9559
- False-positive rate: 0.0833
- Recall: 1.0000
- Precision: 0.9143
- F1: 0.9552
- Confusion matrix: {'tp': 32, 'tn': 33, 'fp': 3, 'fn': 0}

## Gates

| Gate | Value | Limit | Result |
| --- | ---: | ---: | --- |
| vba_accuracy | 0.9558823529411765 | 0.9 | PASS |
| vba_false_positive_rate | 0.08333333333333333 | 0.1 | PASS |
| single_chain_p95_ms | 10.550412500379025 | 200.0 | PASS |
| all_components_present | 6 | 6 | PASS |
| all_baselines_ready | 1 | 1 | PASS |
| fusion_component_checks | 1 | 1 | PASS |
| false_positive_rate_not_above_baseline | 0.08333333333333333 | 1.0 | PASS |
| recall_not_unexplained_drop | 1.0 | 0.95 | PASS |

## Traceability

- Gated AI alerts: 24
- Isolated spatial suppressions: 0
- Detector failures: 0
- Processing p95: 10.550 ms

synthetic fixtures, not real VBA structural-response accuracy
