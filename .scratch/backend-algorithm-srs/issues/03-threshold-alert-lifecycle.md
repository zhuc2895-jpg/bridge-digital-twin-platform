# 03: 物理阈值检测与告警生命周期

**What to build:** 对四类传感器执行三级物理阈值检测，允许运行时修改阈值，并按唯一告警 ID、级别冷却、存储上限和查询排序形成完整告警生命周期。机器客户端可以查询最近 20 条告警、指定时段告警和告警统计。

**Blocked by:** 01

**Status:** ready-for-agent

- [x] 应变、位移、加速度、温度使用黄/橙/红阈值，按读数绝对值比较并只生成命中的最高级别告警。当前数值是临时工程默认值，权威 SRS 来源见工单 15。
- [x] 四类传感器的全部级别阈值均可通过接口读取和修改，修改后下一条读数立即按新阈值判断。
- [x] 同一传感器在 10 秒冷却期内不重复生成同级别告警，冷却结束后可再次生成。
- [x] 每条告警包含唯一 ID、传感器标识与名称、级别、消息、当前值、阈值、规则来源和时间戳。
- [x] 告警最多保留 50000 条；最近 20 条接口和时段查询均按时间倒序返回，时段查询数量与真实记录一致。
- [x] 告警统计基于全部已存储告警，而不是仅基于最近 20 条。
- [x] 覆盖正常值、三个阈值边界、冷却期、冷却结束、存储淘汰和倒序查询的测试。

## Comments

- 2026-10-26: Implementation landed in `f2a97b7`; follow-up TDD changes correct event-time eviction and narrow request-validation scope. Design boundaries are recorded in `CONTEXT.md` and ADRs 0001-0002. Numeric thresholds remain provisional pending issue 15.
- 2026-10-26: Follow-up TDD aligned the implementation with ADRs 0001-0002: unified rule/AI lifecycle entry, UUIDv4 IDs, cross-source event-time cooldown, canonical source and level stats, strict threshold ordering, cooldown invalidation on threshold change, stable detection-order ties, and backend-trusted alert ordering in the frontend.
