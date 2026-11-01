---
status: accepted
---

# System Acceptance Baseline

System acceptance is one reproducible command, `python -m benchmarks.acceptance`. It runs the full pytest suite, API performance gates, detector latency, concurrent API and WebSocket load, and the versioned validation-dataset gates. Every run writes JSON and Markdown with environment details, Git revision, dataset identity and hash, thresholds, reproduction command, per-gate results, and a non-zero exit reason on failure.

The performance batch uses the canonical 10,000-reading steady-normal fixture because this is the established ingestion acceptance fixture and exercises persistence commits as well as the normal-data fast path. Single-reading three-layer detector latency is measured separately after baseline warm-up. WebSocket acceptance uses ten clients for five seconds and requires at least four frames per client and event-time-to-receive p95 below 500 ms.

The synthetic 24-hour validation dataset is versioned by manifest and SHA-256. Its baseline algorithm gate uses the production physical-threshold rule layer with a two-minute, five-alert confirmation window. Raw unaugmented metrics are reported beside confirmed metrics. Full fusion-enhanced AI acceptance is a separate ticket and must not be conflated with this rule-layer baseline.

## Considered Options

- Using only in-process ASGI calls was rejected because HTTP and WebSocket transport behavior are part of the acceptance claim.
- Hiding failed or skipped gates was rejected; skipped required gates produce a failed acceptance result.
- Treating synthetic validation as real bridge accuracy was rejected; reports carry that limitation explicitly.

## Consequences

- Acceptance runs must leave generated reports untracked unless a release explicitly archives them.
- The 24-hour stability probe is an operator entry rather than part of every short CI run; its smoke mode validates the same path quickly.
- Future database persistence or model changes must continue to satisfy the same externally visible gates or revise them through review.
