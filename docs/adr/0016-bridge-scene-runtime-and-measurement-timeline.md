---
status: accepted
---

# Bridge Scene Runtime and Measurement Timeline

The bridge visual scene now has one runtime seam. `BridgeSceneRuntime` owns the Three.js renderer, camera, controls, model loading sequence, bundled structural repair, sensor markers, Pressure Field overlay, picking, animation, resize handling, and resource disposal. App keeps layout, monitoring data, popup copy, and API orchestration. The runtime consumes the active Bridge Scene Profile and never becomes a second spatial authority.

The measurement trend now has one role-keyed timeline. `MeasurementTimeline` stores bounded history by Measurement Role, resets when the active profile identity or role mapping changes, and serves both live and replay appends. `measurementChart` owns the ECharts lifecycle and loads only the line, grid, tooltip, axis-pointer, and canvas modules actually used by the trend.

## Consequences

- Model switching cannot leave the previous bridge's history in the live trend.
- Dialog, chart, and scene code no longer construct Three.js resources or ECharts options inline.
- Sensor rings are indexed by identifier instead of scanned from the scene on every animation frame.
- Pressure textures and the pixel buffer are reused when the grid size is unchanged.
- The production JavaScript bundle no longer imports the full ECharts package.
- ADR-0012 and ADR-0014 remain authoritative for model import and Bridge Scene Profile semantics.
