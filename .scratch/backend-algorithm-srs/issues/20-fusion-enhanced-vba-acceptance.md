# 20: 融合增强后的 VBA 回归验收

**What to build:** 将认知度门控、空间残差、仿真补偿和全场反演能力接入现有 VBA 验收体系，冻结优化前基线并比较增强后的准确率、误报率、召回率、置信度校准和推理性能，确保新增能力产生可解释收益而不是只增加复杂度。

**Blocked by:** 16, 17, 18, 19

**Status:** ready-for-agent

- [x] 保存并版本化融合增强前的 VBA 基线结果和代码版本。
- [x] 增强后的运行必须包含全部新增组件，并报告逐录音、逐折和总体指标。
- [x] 误报率不得高于优化前基线，准确率不得低于 SRS 门槛，召回率不得出现未解释的明显下降。
- [x] 输出认知度、空间残差和补偿可靠性的校准分析，验证高不确定度样本确实对应较高错误或异常风险。
- [x] 确认低认知度降级和空间残差抑制在报告中可追溯，而不是通过隐藏告警虚增指标。
- [x] 报告新增组件的推理耗时、内存变化和失败回退次数，单条完整链路仍满足 200ms 预算。
- [x] 提供单命令复现入口和机器可读结果，任一验收门槛失败时返回非零退出码。
- [x] 报告明确合成夹具结果与真实有限元/标定数据结果，二者不得混为一谈。

## Comments

- 2026-11-01: Added detector state snapshotting, orchestration scripts, per-fold evidence caching, frozen `benchmarks/vba/baseline-v1.json`, enhanced `benchmarks/vba/enhanced-v1.json`, and ADR/report updates. The frozen baseline records its pre-enhancement commit, disabled cognition/spatial configuration, clean execution commit, and raw alert metrics. The enhanced pipeline trains evidence on each fold's out-of-fold INT recordings, feeds cognition/uncertainty/spatial/gate evidence plus resampled multichannel sequences into an out-of-fold supervised fusion classifier, and keeps raw unsupervised alert metrics beside it. Enhanced metrics: accuracy 0.9706, FPR 0.0556, recall 1.0, F1 0.9697 (TP 32, TN 34, FP 2, FN 0); baseline accuracy 0.4706, FPR 1.0, recall 1.0. Gated alerts 31, whole-chain p95 8.78 ms, compensation 15.7 ms and modal inversion 0.36 ms component timings, 16.2 MB memory change, two compensation fallbacks, no detector failures, and all component/baseline gates passed. Synthetic compensation/modal checks are separately labeled and not presented as real VBA accuracy.
- 2026-11-01: Regenerated both artifacts after the ticket-15 design-basis wiring so their `threshold_profile_version` is `code-derived-v1-pending-signoff`, and the evidence cache now validates that version. Baseline still reproduces the expected pre-enhancement failure (accuracy 0.4706, FPR 1.0, recall 1.0). Enhanced still passes every gate with accuracy 0.9412, FPR 0.0833, recall 0.9688, F1 0.9394 (TP 31, TN 33, FP 3, FN 1), whole-chain p95 6.31 ms, 358 gated alerts, zero isolated spatial suppressions, zero detector failures, and all component/baseline gates passing. The metric shift from the earlier run is attributable to the stricter design-basis thresholds, not to component changes.
- 2026-11-01: Made the compensation calibration explicit in the machine-readable artifact: `calibration.compensation_reliability` now carries the low/medium/high reliability bins and their MAE/sample counts next to cognition and spatial calibration. Added a contract test over `enhanced-v1.json`; baseline and enhanced artifacts were regenerated.
