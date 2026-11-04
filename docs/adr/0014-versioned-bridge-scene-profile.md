---
status: accepted
---

# Versioned Bridge Scene Profile

Every bridge model now has one versioned Bridge Scene Profile as the authoritative spatial interpretation for rendering, Sensor Anchors, Measurement Roles, and Response Pressure Field bounds. The profile uses a right-handed metre frame with X longitudinal, Y up, and Z transverse. It records explicit translation, rotation, scale, source unit scale, deck bounds, sensor anchors, measurement roles, and display metadata; it does not store an opaque transform matrix.

The bundled model uses a hand-authored profile. Imported models may include an explicit sidecar profile or receive one later through the profile endpoint. When no profile exists, the model store infers a provisional profile from glTF node transforms, accessor bounds, and deck/girder naming, persists it as revision one with `source: inferred`, and allows later explicit replacement. Profiles are immutable revisions; replacement creates a new revision and Active Bridge Model responses expose only its revision and URL.

Imported models render at the physical scale described by their profile rather than being normalized to a fixed 240 units. Sensor markers, camera fit, pressure overlay placement, pressure grid bounds, chart roles, and popup metadata consume the same profile. The backend Pressure Field reads the active profile directly, so scene and field cannot disagree about deck bounds or sensor anchors.

Profile validation, inference, or model loading failure is explicit. The frontend does not silently fall back to fixed 240m geometry, fixed deck bounds, or default cable positions. A missing profile may enter the inferred path, but a failed inference or invalid explicit profile is surfaced as a scene error.

## Consequences

- ADR-0012's blanket "reuse the same pressure overlay placement" consequence is narrowed: placement is shared through the active Bridge Scene Profile, not through fixed bundled geometry.
- Changing a model's spatial interpretation requires a profile revision rather than a frontend heuristic change.
- Historical pressure fields are evaluated against the currently active profile and state that provenance explicitly.
