# 17: 多传感器空间残差仲裁

**What to build:** 从正常传感器数据学习测点之间的空间重建关系，为每个传感器计算由其他传感器预测其读数时的标准化残差。将空间一致性作为第三层仲裁证据，使孤立传感器噪声更难被升级为结构异常，同时保留多个测点一致变化的真实异常告警能力。

**Blocked by:** 08

**Status:** ready-for-agent

- [x] 使用正常读数训练跨传感器重建模型，覆盖 8 个测点并支持缺失一个或多个传感器时的安全降级。
- [x] 对每个读数计算预测值、实测值、标准化残差和空间一致性状态。
- [x] 仲裁结果携带空间残差证据，并与均值偏移、方差变化率、趋势斜率共同形成最终结论。
- [x] 单传感器孤立尖峰或噪声不得仅因时间序列模型投票而升级为橙/红告警。
- [x] 多传感器符合同一结构变化模式时，仍可确认异常并保留原有级别能力。
- [x] 空间残差阈值、参与传感器最小数量和权重可配置，模型在训练不足时返回未就绪而非误报。
- [x] 覆盖单传感器噪声、多传感器共同漂移、缺失通道、训练不足、正常稳定数据和传感器故障的测试。
- [x] 在 VBA 基准上报告加入空间残差前后的误报率、召回率和逐传感器告警数量。

## Comments

- 2026-11-01: Added the cross-sensor ridge reconstruction adapter with missing-channel degradation, per-reading predicted/actual/residual/standardized residual, marginal outlier localization, coherent-versus-isolated status, configurable weights/thresholds/minimum sensors, and arbitration evidence. Isolated spatial outliers cap confirmed time-series decisions at yellow; coherent multi-sensor changes retain orange/red capability. Added spatial tests, configuration coverage, and VBA before/after artifact fields including per-sensor/source/level counts. Latest enhanced VBA report: FPR 0.0833 versus baseline 1.0, recall 1.0 versus 1.0, accuracy 0.9559; per-sensor counts are in `benchmarks/vba/enhanced-v1.json`.
