---
status: accepted
---

# Known and Online Sensor Metrics

Monitoring surfaces need both a stable equipment inventory and a live connectivity indicator. A **Known Sensor** is therefore distinct from an **Online Sensor**: the former has at least one Sensor Reading in the current process, while the latter has a latest reading within the provisional 60-second Online Sensor Freshness interval of the reference time, in either direction. `sensor_count` remains the known count for compatibility, and a separate online count is exposed. Sensor connection state remains independent from Sensor Physical State.

The HTML report separately shows Cumulative Reading Count and Period Reading Count. Both use Sensor Reading timestamps across every ingestion path, so simulation, uploads, backfill, and manual injection contribute consistently.

## Considered Options

- Defining online as active within the report period was rejected because the same sensor would change connection state when the report window changed.
- Redefining `sensor_count` as online was rejected because it would silently change an existing API contract and discard the known-device inventory.
- Counting readings by ingestion time was rejected because report periods and historical replay use event time.

## Consequences

- A timestamp more than 60 seconds in the future is offline and time-invalid rather than permanently online.
- Physical state ignores time-invalid future readings; it falls back to the latest time-valid reading, or unknown when none exists.
- Sensor-facing tables must present connection state and physical state separately.
- The 60-second freshness value is provisional and moves to the shared configuration layer when that layer exists.
