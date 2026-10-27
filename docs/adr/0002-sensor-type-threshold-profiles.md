---
status: accepted
---

# Sensor-Type Threshold Profiles

Physical thresholds are shared by every sensor of a given type rather than configured per sensor. Each profile contains strictly increasing, finite, positive yellow, orange, and red values. Strain is measured in microstrain (µε), displacement in millimetres (mm), acceleration in metres per second squared (m/s²), and temperature in degrees Celsius (°C).

The current numeric values are provisional engineering defaults because no authoritative SRS threshold table exists. They remain normal API values without provenance metadata; their provisional status is documented here and tracked by the threshold-source follow-up issue. Threshold updates are atomic and do not alter retained alert snapshots.

## Consequences

- Future per-sensor overrides require a separate decision and must define how they compose with type-wide defaults.
- Equal or reversed threshold levels are rejected because they would make one or more alert levels unreachable.
- Obtaining authoritative values can change defaults and tests without changing the alert lifecycle contract.
