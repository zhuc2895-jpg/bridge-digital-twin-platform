---
status: accepted
---

# Threshold Provenance

A threshold profile is not authoritative merely because it has numeric values. Every profile carries provenance: status (`provisional` or `authoritative`), profile version, source document/version/section, effective date, approving engineering owner, scope, units, and notes. Authoritative provenance is rejected unless all source and approval fields are present and the effective date is ISO `YYYY-MM-DD`.

The current defaults remain `provisional-default-v1` with no source document, effective date, or approver. They are exposed through `GET /api/data/config/threshold-profile` and health so clients do not mistake runnable engineering defaults for approved limits. Runtime threshold changes remain operational overrides and do not upgrade provenance.

An authoritative rollout can point `BRIDGE_THRESHOLD_PROFILE_PATH` at one JSON document containing both `thresholds` and `provenance`. That document is the single source of truth for values and source metadata; combining it with individual `BRIDGE_{TYPE}_{LEVEL}` overrides or a separate `BRIDGE_THRESHOLD_PROVENANCE_JSON` is rejected so the recorded provenance cannot silently diverge from the active values.

## Consequences

- Ticket 15 cannot become authoritative until an external SRS, design-code clause, or signed threshold table supplies the required metadata and values.
- Any future authoritative value replacement must update provenance, units, tests, and documentation in the same change.
- Provisional profiles remain usable, but reports and APIs must label them as provisional.
