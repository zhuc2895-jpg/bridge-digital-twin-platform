---
status: accepted
---

# Runtime Configuration and Safe Observability

Runtime settings come from one `AppConfig` object built from validated defaults and `BRIDGE_*` environment variables. The object owns host, port, checkpoint path, log level, CORS whitelist, simulator switch, live interval, physical threshold profiles, AI vote thresholds, and feature-arbitration thresholds. Configuration validation fails fast with a clear error instead of silently accepting unsafe values.

CORS uses an explicit origin whitelist with credentials enabled; a wildcard origin is rejected. Each HTTP request receives a bounded request identifier, which is returned in `X-Request-ID` and included in request logs. Unhandled failures return a stable public error body containing only an error code, generic message, and request identifier. Internal exception type and redacted message are logged, not returned.

Application logs pass through a filter that redacts common credential forms and caps individual messages. Request logs contain method, path, status, duration, and request identifier, but never headers, request bodies, or full payloads. Health reports `degraded` when a detector or persistence dependency reports a failure while the process can still serve requests.

## Considered Options

- Wildcard CORS with credentials was rejected because it defeats origin isolation and is invalid for credentialed browser requests.
- Logging full invalid uploads was rejected because it can expose credentials and creates unbounded log volume.
- Returning stack traces to API clients was rejected because it exposes internals and file paths.
- Treating any dependency error as process death was rejected; local detector or checkpoint failures should degrade observability without dropping available monitoring data.

## Consequences

- Production deployments must list every browser origin explicitly.
- A simulator-disabled deployment keeps upload, query, history, report, and alert APIs available but does not autostart simulator frames or accept manual injection.
- Operators diagnose internal failures from request identifiers and redacted logs rather than client-visible stack traces.
