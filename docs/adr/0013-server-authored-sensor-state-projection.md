---
status: accepted
---

# Server-Authored Sensor State Projection

Physical and connection state are now derived once at the engine read seam rather than in each consumer. The engine pairs each projected Sensor Reading with its Sensor Physical State and Sensor Connection State under the active Threshold Profile. This removes hard-coded frontend thresholds, makes negative readings follow the same absolute-value rule as alerts, applies per-sensor overrides consistently, and keeps ADR-0006's physical/connection separation intact.

The projection is computed at read time under the shared processing lock. It is not persisted and no derived state cache exists, so runtime threshold changes apply on the next Live Tick or REST read without invalidation. Missing thresholds, incomplete threshold bands, type-mismatched sensor overrides, non-finite values, and time-invalid future readings project as unknown rather than falling back to normal.

Live Frames remain additive at the wire level: every sensor reading gains `physical_state` and `connection_state`, and the frame carries one compact `threshold_profile` object with profile version and provenance status. Historical snapshots use the active Threshold Profile and evaluate connection state at the requested historical timestamp; live surfaces evaluate connection state at the current server time. Response Pressure Fields consume the same projected physical state, and their `max_level` is the highest known contributing state rather than a separate fixed-ratio policy.

If one reading fails projection, only that reading becomes unknown and the original value remains available. If no pressure contributor has a known state, the pressure field reports `max_level: unknown`. The Live Frame is still published; projection failure must not become a silent stream outage.

## Consequences

- Threshold policy lives in one module at the engine seam; callers consume state rather than recomputing it.
- Historical physical state means "evaluated against the active profile", not a reconstruction of the threshold version at event time.
- Wire payloads gain compact state fields and profile metadata; the existing 10KB framing policy remains the budget authority.
- Tests can assert Live Frame, historical snapshot, and Response Pressure Field agreement from one projection interface.
