---
status: accepted
---

# Real-Time Response Field and Bridge Model Import

The real-time pressure cloud is a normalized Response Pressure Field, not a finite-element pressure or stress result. Each Live Sensor Snapshot reading contributes `abs(value) / red_threshold`, and inverse-distance weighting interpolates those ratios over a 25 x 9 deck-plane grid. This lets strain, displacement, acceleration, and temperature sensors share one bounded visual scale while preserving their configured engineering thresholds. The field is explicitly labelled as a visualization index so operators cannot mistake it for measured pressure.

The field travels inside the existing `sensor_update` Live Frame as an optional `pressure` member. It is omitted when the combined payload would exceed the 10KB frame budget. Keeping one frame per Live Tick preserves the existing slow-client, latency, and WebSocket sequencing contracts; a second high-frequency message type would have doubled queue pressure and broken consumers that assume one frame per tick.

Imported bridge models are validated self-contained glTF 2.0 assets (`.glb` or `.gltf`). GLB headers and JSON chunks are checked, and glTF external buffer or image URIs are rejected because the import endpoint stores one file. Imports are capped at 100MB, assigned opaque IDs, written atomically, and tracked in an index with at most one Active Bridge Model. The bundled model remains available when no import is active. The frontend loads the active model through the API and shares pressure overlay placement through the active Bridge Scene Profile defined by ADR-0014.

The Windows Desktop Distribution runs the same FastAPI application locally and serves the built frontend from the packaged distribution at `/app`; it does not fork a separate UI contract. The launcher stores checkpoints and imported models under `%LOCALAPPDATA%\BridgeDigitalTwin`, selects a free loopback port, and hosts the page in a native WebView.

## Consequences

- The pressure cloud is an operational visualization aid until calibrated against finite-element and field data.
- Large alert payloads can cause the optional `pressure` member to be omitted; the REST response-field endpoint remains available.
- Imported models must be self-contained; external `.bin`, texture, and other sidecar resources must be embedded or exported as GLB.
- Packaging must rebuild `frontend/dist` before PyInstaller so the desktop executable and browser deployment share one frontend contract.
