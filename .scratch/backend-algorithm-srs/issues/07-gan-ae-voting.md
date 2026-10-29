# 07: GAN-AE 检测器与三模型投票

**What to build:** 增加基于重构误差的 GAN-AE 检测器，并将 STALWART-inspired、GAN-AE、Isolation Forest 接入多数投票。至少两个模型确认且满足置信度门槛时生成统一 AI 告警，保存触发模型、置信度、分数和 SRS 规定的来源标识。

**Blocked by:** 05, 06

**Status:** ready-for-agent

- [x] GAN-AE 从每传感器基线正常窗口学习重构分布，以当前重构误差超过历史均值加 3 倍标准差判定异常。
- [x] 三个模型各自输出明确的票；仅有置信度不低于 0.7 的模型票计入多数投票。
- [x] 至少两票时生成 AI 告警，告警来源映射为 `ai_stalwart`、`ai_gan_ae`、`ai_isolation_forest`、`ai_dual_confirm` 之一并保留参与模型信息。
- [x] 正常稳态数据在基线完成后不产生 AI 告警；SRS 规定的突变异常至少触发两个模型。
- [x] 单条数据完成三层检测的纯推理耗时不超过 200ms，并在测试中记录耗时。
- [x] 覆盖单票、双票、三票、低置信度票、模型未就绪和正常数据测试。

## Comments

- 2026-10-29: Implemented a per-sensor adversarial GAN-AE reconstruction detector, confidence-gated three-model majority voting, canonical `ai_dual_confirm` alerts with retained per-model diagnostics, vectorized batch inference for ingestion performance, and coverage for one/two/three votes, low confidence, unready models, steady data, alert persistence, and sub-200ms inference. The issue's shorthand `ai_iforest` is normalized to the accepted canonical source `ai_isolation_forest`.
