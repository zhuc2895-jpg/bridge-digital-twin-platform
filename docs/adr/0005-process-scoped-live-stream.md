---
status: accepted
---

# Process-scoped 1Hz live stream

Bridge monitoring needs one shared real-time state without duplicating simulation, ingestion, or alerts, while the dashboard needs a predictable 1Hz update cadence. The backend therefore uses one Live Stream Loop per application process, emits one bounded Live Frame per second, and treats uploads and injections as state mutations rather than immediate WebSocket messages.

## Considered Options

- **Per-client loops** were rejected because each connection would regenerate and re-ingest data, risking duplicate alerts and divergent state.
- **Immediate `sensor_update` frames for uploads or injections** were rejected because they break the 1Hz cadence and make frame sequences client-dependent.
- **Cached replay or catch-up frames** were rejected because late clients would receive off-cadence stale frames.
- **Unbounded per-client queues** were rejected because slow subscribers could grow memory without bound.
- **Full alert evidence and unbounded text in Live Frames** were rejected because the frame must remain within 10KB.
- **A multi-worker shared broker** was deferred; supporting it requires a separate distributed state and fan-out design.

## Consequences

- Deployment uses a single backend worker; each process owns its own live state, and health reporting identifies state scope as process-local.
- `sensor_update` is strictly 1Hz. Uploads and manual injections update shared state and are observed on the next Live Tick.
- The former `push_live` flag marks whether uploaded readings are Live Eligible; it no longer requests an immediate frame.
- A Live Sensor Snapshot contains the latest Live Eligible reading per sensor, ordered by event time and limited to the 32 most recent sensors.
- A Live Frame contains at most 20 Realtime Alert Projections from Live Eligible data; backfill alerts remain available through REST and history queries.
- Live Frames use bounded text, omit full alert evidence, encode standard JSON only, and never exceed 10KB. If a valid bounded frame cannot be produced, that tick is logged and skipped.
- New clients wait for the next global tick. Slow clients are disconnected when their bounded queue fills, a frame goes stale, or sending exceeds the 500ms latency budget; close tasks are tracked and timed out.
- Shared engine and detector mutations use one serialized boundary. Stable snapshots are copied under that boundary, and expensive JSON encoding occurs outside it.
- The frontend may optimistically show a pending mutation result, but the next Live Frame replaces it with server state.
