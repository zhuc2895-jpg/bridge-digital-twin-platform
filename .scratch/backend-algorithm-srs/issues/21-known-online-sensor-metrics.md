# 21: Known/Online Sensor metrics and report reading scopes

**What to build:** 把“已知传感器”“在线传感器”和两种读数口径落实到引擎、健康检查、HTML 报告和前端看板，确保同一术语在所有入口表达同一含义，同时保持现有 `sensor_count` API 兼容。

**Blocked by:** 11

**Status:** ready-for-agent

- [x] 引擎区分 Known Sensor Count 与 Online Sensor Count；在线判定以请求参考时间为基准，最新 Sensor Reading 在参考时间前后 60 秒内均算在线，超过 60 秒的未来时间戳判为离线且标记时间异常。
- [x] 60 秒 Online Sensor Freshness 使用单一命名常量，默认 60 秒；暂不新增运行时配置机制。
- [x] `sensor_count` 保持为 Known Sensor Count；健康检查新增 `online_sensor_count`，前端看板的“传感器在线”改用在线数。
- [x] HTML 报告以报告结束时间作为在线参考时间，展示 Online Sensor Count；同时展示 Cumulative Reading Count 与 Period Reading Count，时段边界为闭区间。
- [x] 两种读数均按 Sensor Reading 时间戳统计全部摄入路径；Cumulative Reading Count 在新进程启动时归零，Period Reading Count 只统计报告时段内读数。
- [x] 传感器表拆分“连接状态”和“物理状态”；离线传感器保留最后物理状态，但物理状态只取最新 Time-Valid Sensor Reading，跳过未来超过 60 秒的无效读数；没有时间有效读数时显示“未知”，不把连接状态混入物理状态。
- [x] 覆盖 60 秒前后边界、未来时间异常、时段起止边界、时段外数据、跨摄入路径、进程重启归零、报告与看板/健康检查一致性测试。

## Comments

- 2026-11-01: Split from the review follow-up to issue 11. The glossary and ADR-0006 now define Known Sensor, Online Sensor, connection state, physical state, Cumulative Reading Count, and Period Reading Count.
- 2026-11-01: Implemented the shared 60-second freshness rule, Known/Online counts, locked health snapshot, Cumulative and Period Reading Counts, split connection/physical report states, and dashboard online counts. Physical fallback has an independent latest-time-valid cache so full-history eviction cannot hide the last valid reading, and future readings become valid as the reference advances. Verification: full backend suite 249 passed; mypy and targeted Ruff passed; frontend production build passed.
