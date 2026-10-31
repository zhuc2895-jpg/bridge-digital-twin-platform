# 10: 单一实时采集循环与多客户端 WebSocket

**What to build:** 将实时数据生产与客户端连接解耦：后端只运行一个仿真/摄入循环，所有 WebSocket 客户端共享同一份实时状态。连接后以 1Hz 推送 `sensor_update` 消息，支持多客户端、断线清理、消息大小限制和采集循环异常隔离。

**Blocked by:** 08, 09

**Status:** ready-for-agent

- [x] 任何数量的 WebSocket 客户端都只对应一个数据生成与摄入循环，不会因新增连接而重复生成、重复摄入或重复告警。
- [x] 至少 10 个客户端可同时连接，并在连接后以 1Hz 接收同一批次传感器数据、最近 20 条告警和系统统计。
- [x] `sensor_update` 消息包含 `type`、`sensors`、`alerts`、`stats`，单条消息不超过 10KB。
- [x] 客户端断开、发送失败或异常关闭后连接资源被清理；重复连接和断开不形成内存增长。
- [x] 单次推送从数据生成到客户端接收的延迟不超过 500ms。
- [x] 采集循环中的单条坏数据或 AI 错误被隔离并记录，不终止其他客户端，也不终止后续推送。
- [x] 覆盖单客户端、10 客户端、广播一致性、断线清理、消息契约和大小上限的自动化测试。

## Comments

- 2026-10-31: Implemented one application-scoped live simulation/ingestion thread started by the FastAPI lifespan, independent of WebSocket connection count. Clients subscribe through per-client bounded send queues; each healthy client receives the same 1Hz `sensor_update` frame, while cached frames older than 500ms are not replayed and stale queued frames are skipped. Slow clients are disconnected instead of silently receiving divergent frame sequences. Payload construction now enforces the 10KB UTF-8 cap with recent-20 alerts, and malformed live records or detector/processor failures are logged and isolated without stopping later frames. Added regression coverage for single/multi-client broadcast consistency, duplicate-alert prevention, connection cleanup, message contract/size, 1Hz cadence, generation-to-receipt latency, late joins, no-client autostart, and bad-record/AI failure recovery. Full backend suite: 178 passed.

- 2026-10-31: Review follow-up. Removed cached-frame replay so a newly connected client starts on the next global 1Hz tick instead of receiving an off-cadence replay. Slow or stale clients are now disconnected and their ASGI WebSocket is actively closed on send failure, queue overflow, or stale-frame detection, preventing routes from remaining blocked in receive_text(). The bounded sensor_update builder now always preserves all 20 recent alerts and the full eight-sensor live frame before dropping sensors, and live frame validation now reuses the same strict JSON ingestion mapper as API uploads. Added manager-level coverage for ten-client sustained identical broadcasts, send-failure cleanup, queue-overflow cleanup, stale-frame cleanup, and no cached replay. Verification: mypy passed 49 files, ruff passed, full suite 185 passed.

- 2026-10-31: Structure follow-up from review. Extracted `LiveStreamRunner` from the dependency container, centralized REST/live publishing in `SensorUpdatePublisher`, named the payload text limits, renamed `broadcast_now` to `enqueue_broadcast`, removed delegation-only WebSocket APIs and lifecycle wrappers, and shared test polling helpers. Verification: mypy passed 50 files, ruff passed, full suite 185 passed.

- 2026-10-31: Final review hardening. Split the wire contract from the live runner, replaced the service-container host protocol with explicit tick wiring, named the payload text policies, removed the last delegation-only manager API, and centralized test app construction. Threshold updates, detector relearning, uploads, manual injection, live processing, and payload snapshots now share `processing_lock`. `sensor_update` now includes alert `details` and keeps the full alert record when it fits; the 10-client end-to-end test validates three consecutive identical frames, all 20 alerts, 1Hz generation, and sub-500ms generation-to-receipt latency. Mypy/Ruff moved to `requirements-dev.txt`. Verification: mypy passed 51 files, ruff passed, full suite 187 passed.
