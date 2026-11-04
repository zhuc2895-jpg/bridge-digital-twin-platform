---
status: accepted
---

# Stable History Reads and Analysis Execution

History, retained snapshots, alerts, latest readings, and report state are read through `HistoryReadModel`. It acquires the shared processing lock around each stable result and exposes intent-level reads rather than leaking route-specific lock policy. The report consumes one `ReportReadSnapshot`, and timestamp-aware analysis distinguishes unavailable history, out-of-range timestamps, and missing snapshots through domain errors mapped by the route.

Blocking analysis and report work runs through `AnalysisExecutor`. Production uses `ThreadedAnalysisExecutor` to move response estimation, modal inversion, Pressure Field construction, history scans, and report rendering off the event loop. Tests can replace it with `InlineAnalysisExecutor` or a recording adapter without changing route logic.

## Consequences

- History reads observe one mutation boundary instead of a route-selected subset of locks.
- Analysis and report requests no longer stall Live Frame delivery or health checks.
- The read and execution seams are testable without FastAPI-specific setup.
- ADR-0005 remains authoritative: stable inputs are acquired under the shared lock, and expensive calculation occurs outside it.
