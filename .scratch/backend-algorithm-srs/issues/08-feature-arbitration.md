# 08: 多窗口特征仲裁

**What to build:** 对进入第三层的异常执行可解释的多窗口特征仲裁。仲裁使用近期 20 条与历史 60 条读数计算均值偏移、方差变化率和趋势斜率，至少两个特征越过统计阈值才确认异常，否则标记为疑似并降级处理。

**Blocked by:** 07

**Status:** ready-for-agent

- [x] 同时计算近期窗口 20 条和历史窗口 60 条，并产出均值偏移量、方差变化率、趋势斜率三项特征。
- [x] 每项特征有明确阈值和超限判定；至少两项超限时确认异常，仅一项超限时标记为疑似并降级。
- [x] 仲裁告警包含触发模型、三项特征的数值、超限项和最终结论，来源为 `ai_feature_arbitration`。
- [x] 确认和疑似告警采用正确的级别映射，不得出现异常越严重级别反而更低的情况。
- [x] 使用可复现的稳态、均值漂移、方差突增、趋势变化和单特征异常样本验证仲裁结果。
- [x] 覆盖窗口不足、历史方差接近零、上下异常方向和至少两项超限的测试。

## Comments

- 2026-10-30: Implemented a per-sensor third-layer arbitrator over event-time ordered 60 historical and 20 recent normal readings, with standardized mean shift, variance ratio, and normalized trend slope. Physically abnormal readings are excluded from the arbitration window so rule alerts cannot contaminate later decisions. One exceeded feature produces a yellow suspected alert, two produce an orange confirmation, and three produce a red confirmation; every candidate alert retains its trigger model, feature evidence, thresholds, exceeded features, conclusion, and `ai_feature_arbitration` source through the ingestion alert lifecycle.
- 2026-10-30: Closed review gaps test-first: batch inference now orders readings by sensor and event time before running stateful models, the 20/60 windows are fixed by validation, `detect_one` and `detect_batch` share the same physical-rule filter, and `trend_slope` now exposes the raw regression slope while its normalized threshold remains in the evidence.
- 2026-10-30: Completed the second review pass test-first: later backfills rebuild stateful model state from retained event-time history, constructor-level physical-rule predicates are forwarded to the inner detector, and the fixed-window/test-stub cleanup removes the remaining review smells.
- 2026-10-30: Closed the final review pass test-first: baseline-learning samples join the replay history, all real readings including physical-rule anomalies enter the 20/60 arbitration window, and public detection statistics exclude internal replay work. Per-sensor history state and event-time execution mapping were consolidated during refactoring.
