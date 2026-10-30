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

- 2026-10-30: Implemented a thread-safe per-sensor FIFO of one-shot anomaly injections. Each queued reading is generated at 2.5–4× the normal sample plus a 50–150 offset, consumed exactly once by a complete simulator frame, and then the sensor returns to its normal stream. The API accepts a body or query sensor identifier, rejects unknown or conflicting identifiers with 400, and queues work through the same simulator data path used by WebSocket ingestion. End-to-end coverage now drives the production WebSocket loop through physical thresholds, a deterministic three-model single-vote case, real feature arbitration, and recent/range alert queries, alongside boundary, recovery, producer-concurrency, and frame-consumption tests.
