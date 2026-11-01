---
status: accepted
---

# Sensor-Type Threshold Profiles

Physical thresholds are shared by every sensor of a given type rather than configured per sensor. Each profile contains strictly increasing, finite, positive yellow, orange, and red values. Strain is measured in microstrain (µε), displacement in millimetres (mm), acceleration in metres per second squared (m/s²), and temperature in degrees Celsius (°C).

The current numeric values are provisional engineering defaults because no authoritative SRS threshold table exists. They remain normal API values without provenance metadata; their provisional status is documented here and tracked by the threshold-source follow-up issue. Threshold updates are atomic and do not alter retained alert snapshots.

## Consequences

- Per-sensor overrides were accepted by ADR-0011 and the ticket-15 design basis: a Sensor Threshold Override applies only to its declared sensor type and takes precedence over the type profile; other sensors keep the type profile.
- A type-level runtime override (`BRIDGE_{TYPE}_{LEVEL}` or `POST /api/data/config/thresholds`) switches that running instance to type-wide tuning and clears the default sensor-specific overrides, so the update is never silently masked.
- Equal or reversed threshold levels are rejected because they would make one or more alert levels unreachable.
- Obtaining authoritative values can change defaults and tests without changing the alert lifecycle contract.
