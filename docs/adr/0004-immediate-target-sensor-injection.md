---
status: accepted
---

# Immediate target-sensor injection

Manual anomaly injection generates and processes an **Injected Reading** immediately for one specified sensor, advancing only that sensor's stream position. It does not queue work for a global simulation frame, so the alert is queryable when the request succeeds and injection does not depend on an active WebSocket consumer.

## Considered Options

- **Immediate per-sensor injection**: predictable API behavior, independent of connection state, and no unrelated sensor readings are created.
- **Queued injection for the next global frame**: preserves frame-wide ordering, but makes API behavior depend on the simulator consumer and creates competing ownership between REST and WebSocket loops.

## Consequences

- A successful injection has already generated and processed its target reading; responses must describe it in the past tense.
- All paths that mutate the shared monitoring engine and detector state share one serialized processing boundary.
- The future single real-time loop must treat REST injection as an operation on the same monitoring pipeline rather than starting a separate ingestion path.
- Automatic simulator anomalies remain separate from manual injection and must not be broken by injection changes.
