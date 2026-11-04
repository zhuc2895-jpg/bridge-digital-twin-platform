---
status: accepted
---

# Live Frame Assembly and Model Import Stream Boundaries

The Bridge Model Store owns the complete import policy. Its `import_stream` interface accepts an owned byte stream and performs the 100MB limit, chunked temporary write, glTF validation, atomic promotion into the model directory, profile initialization, index update, and cleanup. The HTTP route only supplies the upload stream and maps domain errors to status codes. `import_file` and `import_bytes` remain thin adapters so tests and future non-HTTP callers reuse the same invariants instead of maintaining parallel import paths.

The Response Pressure Field module produces only the semantic field. One Live Frame Assembler owns the 10KB UTF-8 frame budget and applies a deterministic degradation order: full frame, pressure without point metadata, no pressure, compact text, minimal text, then removal of the oldest sensors. Every frame carries `budget.limit_bytes` and `budget.omissions`; reduced text precision adds `budget.text_detail`. A Pressure Field production failure is reported as `pressure.failed`, so consumers can distinguish it from budget-driven omission. If required alert content still cannot fit, assembly fails explicitly and the publisher skips that tick rather than emitting an oversized frame.

## Consequences

- Model upload routes no longer know the store root, temporary-file naming, chunk size, size limit, or cleanup rules.
- Pressure field tests can assert semantic content without duplicating frame-budget policy.
- Live Frame consumers can distinguish an absent pressure field from a field that was never produced by reading omission metadata.
- The `sensor_update` wire adds a compact `budget` object to every frame.
- The former 10KB check inside the pressure builder is removed; only the assembler and the transport's defensive size guard enforce the limit.
