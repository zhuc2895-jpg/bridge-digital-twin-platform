---
status: accepted
---

# Threshold Provenance

A threshold profile is not authoritative merely because it has numeric values. Every profile carries provenance: status (`provisional` or `authoritative`), profile version, source document/version/section, effective date, approving engineering owner, scope, units, and notes. Authoritative provenance is rejected unless all source and approval fields are present and the effective date is ISO `YYYY-MM-DD`.

The current defaults are the student-competition S01-S08 design basis: version `competition-design-basis-v1`, status `provisional`, with standard sources recorded but no effective date or approver. `config/bridge-threshold-profile.json` is a versioned mirror of those values; a regression test keeps it content-equivalent to the code default. The defaults are exposed through `GET /api/data/config/threshold-profile` and health so clients do not mistake a runnable competition baseline for an approved production limit. Runtime type-level threshold changes remain operational overrides, clear the default sensor overrides, and downgrade provenance to `provisional-default-v1`; they never upgrade provenance.

An authoritative rollout can point `BRIDGE_THRESHOLD_PROFILE_PATH` at one JSON document containing both `thresholds` and `provenance`, plus optional `sensor_thresholds` for measurements whose authoritative allowable value differs within a sensor type. That document is the single source of truth for values and source metadata; combining it with individual `BRIDGE_{TYPE}_{LEVEL}` overrides or a separate `BRIDGE_THRESHOLD_PROVENANCE_JSON` is rejected so the recorded provenance cannot silently diverge from the active values.

Sensor Threshold Overrides also carry the sensor type they apply to. An override for `S01` is ignored for an acceleration reading mislabeled as `S01`, so a unit mismatch cannot silently apply a strain limit. The effective threshold provenance is part of the persisted engine state; restart recovery restores the provenance that belonged to the restored values rather than relabeling them with the current process configuration.

The source catalogue and formulas are recorded in `docs/thresholds/authoritative-threshold-sources.md`, and the project design basis is derived in `docs/thresholds/sensor-baseline-and-mapping.md`. These standards define relative bases such as historical maxima, design values, and allowable values; they do not supply one universal absolute threshold set. Project design values and engineering sign-off are therefore still required before a profile can become authoritative.

## Consequences

- Ticket 15 is complete for the competition baseline. The toB approval interface remains reserved: a future deployment supplies `approved_by`, `effective_date`, and `status=authoritative` in the same profile document, with no numeric changes.
- Any future authoritative value replacement must update provenance, units, tests, and documentation in the same change.
- Provisional profiles remain usable, but reports and APIs must label them as provisional.
