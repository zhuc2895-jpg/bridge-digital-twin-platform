# VBA Fusion Acceptance

- Mode: enhanced
- Status: **passed**
- Generated: 2026-11-01T07:53:38.905526+00:00
- Reproduction: `python -m benchmarks.vba.evaluate --mode enhanced`
- Git commit: `88a2d53d02ba40805bf33c996cea0de82ddd971b`
- Dataset SHA-256: `BE13A4CAE46E877C6613FABA9ABF164449CFC58EAA73AC86599473EF078FF7A3`

## Overall Metrics

- Accuracy: 0.9706
- False-positive rate: 0.0556
- Recall: 1.0000
- Precision: 0.9412
- F1: 0.9697
- Confusion matrix: {'tp': 32, 'tn': 34, 'fp': 2, 'fn': 0}

## Gates

| Gate | Value | Limit | Result |
| --- | ---: | ---: | --- |
| vba_accuracy | 0.9705882352941176 | 0.9 | PASS |
| vba_false_positive_rate | 0.05555555555555555 | 0.1 | PASS |
| single_chain_p95_ms | 8.782300000348187 | 200.0 | PASS |
| all_components_present | 6 | 6 | PASS |
| all_baselines_ready | 1 | 1 | PASS |
| fusion_component_checks | 1 | 1 | PASS |
| false_positive_rate_not_above_baseline | 0.05555555555555555 | 1.0 | PASS |
| recall_not_unexplained_drop | 1.0 | 0.95 | PASS |

## Traceability

- Gated AI alerts: 31
- Isolated spatial suppressions: 0
- Detector failures: 0
- Processing p95: 8.782 ms

synthetic fixtures, not real VBA structural-response accuracy
