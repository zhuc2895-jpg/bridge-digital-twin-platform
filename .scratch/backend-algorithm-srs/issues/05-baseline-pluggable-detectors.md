# 05: 基线学习与可插拔检测器接口

**What to build:** 为每类检测算法提供统一的可替换检测器接口，并为每个传感器从正常读数中学习基线。系统能公开“学习中/就绪”状态、支持手动重学习，且任一检测器失败时自动降级为物理阈值检测，不中断数据摄入。

**Blocked by:** 01, 03

**Status:** ready-for-agent

- [x] 检测器实现统一契约，至少提供单条/批次检测、统计信息和基线学习能力，可注册、替换并在启动时装配。
- [x] 每个传感器使用前 100 条正常数据建立均值、标准差和 EMA 初值；未满 100 条时状态为学习中且不产生 AI 告警。
- [x] 达到 100 条后状态自动变为就绪，统计接口能返回各传感器学习读数数量和就绪状态。
- [x] 提供手动触发全局或指定传感器基线重学习的接口；重学习期间暂停该传感器 AI 告警，完成后恢复。
- [x] 任一 AI 检测器抛出错误时记录错误、继续完成物理阈值检测，并保持服务与数据摄入可用。
- [x] 覆盖学习状态迁移、手动重学习、检测器替换和检测器故障降级的测试。

## Comments

- 2026-10-28: Implemented a canonical detector contract with registration/replacement and startup assembly, per-sensor first-100-normal-reading baselines, learning/relearning status APIs, rule-first failure isolation, and tests for state transition, EMA calculation, manual relearn recovery, replacement, failure degradation, and anomaly-state rollback.
