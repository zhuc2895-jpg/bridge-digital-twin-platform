---
status: accepted
---

# Atomic Checkpoint Recovery

Monitoring state survives process restarts through a replaceable `CheckpointStore` boundary. The domain engine exports and restores a complete portable state; storage adapters own encoding, atomic replacement, and corruption handling. The default adapter writes one JSON checkpoint to `data/state/monitoring.json` using a same-directory temporary file, file synchronization, and `os.replace`.

Checkpoints include latest and live-visible readings, rolling and full history, reading timestamps, time-valid and future-reading caches, retained alerts, alert cooldowns, and threshold profiles. Processing commits after each successful batch, threshold changes commit immediately, and shutdown performs a final commit. A failed commit is logged and exposed through health status without taking the service offline. A damaged or incomplete checkpoint is logged as a warning, ignored, and replaced by the next successful commit.

## Considered Options

- Writing directly to the destination file was rejected because an interrupted write could destroy the last usable checkpoint.
- Treating persistence as an engine concern was rejected because it would couple queries and detection to a file format.
- Restoring process-lifetime counters was rejected because Cumulative Reading Count intentionally resets with each process.

## Consequences

- The current JSON snapshot is intentionally simple and can be replaced by a database-backed adapter later without changing business modules.
- Each successful processing batch pays checkpoint serialization cost; performance acceptance must measure it with persistence enabled.
- Alert identities, detection order, event-time cooldowns, and threshold configuration remain stable across recovery.
