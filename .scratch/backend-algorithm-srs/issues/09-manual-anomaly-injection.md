# 09: 手动异常注入贯通完整检测链

**What to build:** 提供面向演示和测试的异常注入能力：指定传感器后，其下一条读数按 2.5～4 倍正常值并叠加 50～150 的随机偏移生成，随后完整经过摄入、物理阈值、三模型投票、特征仲裁和告警查询链路。

**Blocked by:** 03, 08

**Status:** ready-for-agent

- [x] `POST /api/analysis/inject-anomaly` 接受有效传感器标识，并对未知传感器返回 400。
- [x] 注入只作用于指定传感器的下一条读数；该读数按指定倍率和偏移范围生成，之后自动恢复正常数据流。
- [x] 注入读数进入与真实读数相同的摄入和检测流程，而非绕过后端直接构造告警。
- [x] 注入后在可查询时间内产生对应级别告警，并能通过最近告警和时段告警接口读取。
- [x] 连续两次注入不会互相污染；并发注入按明确规则处理，不产生重复消费。
- [x] 覆盖有效注入、未知传感器、倍率与偏移边界、一次性消费和完整告警链路的测试。

## Comments

- 2026-10-30: Implemented a thread-safe per-sensor FIFO of one-shot anomaly injections. Each queued reading is generated at 2.5–4× the normal value plus a 50–150 offset, consumed exactly once by a complete simulator frame, and then the sensor returns to its normal stream. The API accepts a body or query sensor identifier, rejects unknown or conflicting identifiers with 400, and queues work through the same simulator data path used by WebSocket ingestion. End-to-end coverage now drives the production WebSocket loop through physical thresholds, a deterministic three-model single-vote case, real feature arbitration, and recent/range alert queries, alongside boundary, recovery, producer-concurrency, and frame-consumption tests.
- 2026-10-30: Review follow-up appended without rewriting prior history. The anomaly endpoint now accepts only a query sensor identifier, and `SensorIdentifier` is used as the validated target identity throughout the simulator queue.
- 2026-10-30: Superseding the preceding follow-up: the endpoint again accepts body or query sensor identifiers, rejects conflicting source values with 400, and retains `SensorIdentifier` as the typed simulator queue key without per-frame reconstruction.
- 2026-10-30: Review follow-up appended without rewriting prior history. Simulator public methods normalize plain string identifiers at their boundary, and each sensor definition now owns a single `SensorIdentifier` through `SimulatorSensor`, removing the parallel identity tuple.
- 2026-10-30: Review follow-up appended without rewriting prior history. Simulator injections now require an explicit target, blank and unknown identifiers share `UnknownSimulatorSensorError`, sensor types use the closed `SensorType` vocabulary, and ingestion reuses `SensorIdentifier` validation.
- 2026-10-30: Review follow-up appended without rewriting prior history. `SensorIdentifier` is now a string-compatible value object, ingestion retains `SensorIdentifier` and `SensorType` through typed sensor readings, the supported type set derives from the single `SensorType` vocabulary, and invalid runtime identifier types raise `UnknownSimulatorSensorError`.
- 2026-10-30: Review follow-up appended without rewriting prior history. The injection endpoint now synchronously generates and processes the next complete simulator frame, so rule and arbitration alerts are queryable without an active WebSocket consumer.
- 2026-10-30: Review follow-up appended without rewriting prior history. REST injection now atomically generates and processes only the requested sensor reading without advancing the full simulator frame; connected WebSocket clients receive the same update through a shared broadcast helper, and concurrent HTTP injections are covered by an exactly-one-reading-per-request test.
- 2026-10-30: Review follow-up appended without rewriting prior history. The simulator now advances independent per-sensor stream ticks; REST injection atomically consumes the target sensor's actual next stream reading, leaves other sensors untouched, and subsequent target readings return to their normal generation path. Concurrent HTTP tests verify distinct injection transforms and exactly two target readings for two requests.
- 2026-10-30: Review follow-up appended without rewriting prior history. Injected readings use the typed `SimulatorReading` payload, the generated injection is consumed through the normal queue path, and an application processing lock serializes generation, detection, cooldown checks, and alert persistence across REST uploads and WebSocket ingestion. Sequential and concurrent HTTP tests now assert both injected alert values exactly once.
- 2026-10-30: Review follow-up appended without rewriting prior history. Explicit injection now returns metadata for the exact reading it generates while leaving any separately queued stream injection untouched, the `pending_injections` response field is restored, and a process-wide re-entrant processing lock covers WebSocket frame generation through alert persistence. Same-level consecutive injections are explicitly tested against the unified alert cooldown ADR: both readings are retained while only one same-level alert is created.
- 2026-10-30: Superseding prior injection-path notes: there is now one injection mechanism. `DataSimulator.inject_anomaly()` atomically advances the target sensor stream and returns `InjectedReading`; the unused FIFO and async generator were removed, and REST always reports `pending_injections: 0`. Processing locks are centralized through the application pipeline.
