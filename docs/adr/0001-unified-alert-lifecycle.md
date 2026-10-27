---
status: accepted
---

# Unified Alert Lifecycle

Physical-rule and AI alerts need one consistent identity, deduplication, retention, and ordering contract. All producers therefore submit alerts through a single lifecycle boundary. That boundary assigns UUIDv4 IDs, applies a ten-second event-time cooldown keyed by sensor and level across all sources, snapshots sensor name and threshold, retains the globally newest 50,000 alerts by event time, and breaks same-time query ties by a monotonic detection sequence.

## Consequences

- Backfilled readings are evaluated against event-time history rather than ingestion time; real-time notification throttling is a separate concern.
- A successful threshold change clears cooldowns for the affected sensor type so the next reading is evaluated under the new policy.
- `recent` alerts are retained historical records, not unresolved incidents; acknowledgement and recovery states are outside this decision.
- Canonical source identifiers are `rule`, `ai_stalwart`, `ai_gan_ae`, `ai_isolation_forest`, `ai_dual_confirm`, and `ai_feature_arbitration`.
- The detection sequence becomes part of persisted alert state when persistence is introduced.
