# VBA Fusion Acceptance

- Mode: baseline
- Status: **failed**
- Generated: 2026-11-01T07:28:17.054521+00:00
- Reproduction: `python -m benchmarks.vba.evaluate --mode baseline --output benchmarks/vba/baseline-v1.json`
- Git commit: `60308e0fc53054a652750021381a264fb66d9b65`
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
| single_chain_p95_ms | 8.521575000486337 | 200.0 | PASS |
| all_components_present | 6 | 6 | PASS |
| all_baselines_ready | 1 | 1 | PASS |
| fusion_component_checks | 1 | 1 | PASS |

## Traceability

- Gated AI alerts: 0
- Isolated spatial suppressions: 0
- Detector failures: 0
- Processing p95: 8.522 ms

synthetic fixtures, not real VBA structural-response accuracy
