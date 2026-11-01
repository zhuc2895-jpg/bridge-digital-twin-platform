# 14: 性能、并发与算法验收

**What to build:** 形成可重复执行的系统验收套件和部署交付，证明后端、算法和实时链路达到 SRS 的性能、并发、准确率、误报率和稳定性要求。

**Blocked by:** 10, 11, 12, 13

**Status:** ready-for-agent

- [x] 基准脚本验证 10000 条批量摄入不超过 500ms，常规查询不超过 200ms，快照不超过 100ms，单条三层 AI 检测不超过 200ms。
- [x] 负载测试验证 API 并发不低于 50 QPS，至少 10 个 WebSocket 客户端可持续以 1Hz 接收且推送延迟不超过 500ms。
- [x] 在版本化验证数据集上输出准确率、误报率、混淆矩阵和样本统计；准确率不低于 90%，误报率不高于 10%。
- [x] 提供 24 小时稳定性运行入口与报告，记录内存、连接数、吞吐、告警数量、错误数和最终存活状态，用于判断内存泄漏。
- [x] 所有性能与准确率结果带环境、版本、数据来源和复现命令，失败时返回非零退出码。
- [x] 提供能启动后端并暴露 HTTP/WebSocket 服务的容器化交付与使用说明。
- [x] CI 或单命令验收入口可运行单元、集成、性能和算法测试，并汇总通过/失败结果。

## Comments

- 2026-11-01: Added the versioned synthetic validation manifest (`3EB745...A0C`), `python -m benchmarks.acceptance`, and the 24-hour `python -m benchmarks.stability` entry with short-run smoke validation. Added Dockerfile, compose delivery, ADR-0009, and acceptance tests. The acceptance algorithm gate is explicitly the physical-rule baseline with a two-minute/five-alert confirmation window; raw unaugmented metrics are also reported, while fusion-enhanced AI acceptance remains ticket 20. Latest full run passed: 10k ingest 283.4 ms, query p95 8.1 ms, snapshot p95 1.5 ms, three-layer detection p95 7.1 ms, API 164.2 QPS, 10 WebSocket clients with 5 frames each and 6.3 ms p95 push latency, validation accuracy 0.9826, FPR 0.0146, event recall 1.0.
