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

- 2026-11-01: Added detector state snapshotting, orchestration scripts, evaluation cache, frozen `benchmarks/vba/baseline-v1.json`, enhanced `benchmarks/vba/enhanced-v1.json`, and ADR/report updates. The enhanced pipeline runs all new components and uses an out-of-fold supervised fusion classifier over resampled multichannel sequences; raw unsupervised alert metrics remain reported beside it. Enhanced metrics: accuracy 0.9706, FPR 0.0278, recall 0.9688, F1 0.9688 (TP 31, TN 35, FP 1, FN 1); baseline accuracy 0.4706, FPR 1.0, recall 1.0. Gated alerts 31, single-chain processing p95 10.43 ms, no detector failures, all component/baseline checks passed. Synthetic compensation/modal checks are separately labeled and not presented as real VBA accuracy.
