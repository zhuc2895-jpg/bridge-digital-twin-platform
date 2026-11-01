# 16: 模型认知度与不确定性门控

**What to build:** 借鉴虚实融合模型中的子学习器方差方法，让 AI 检测不仅输出“是否异常”，还输出模型对该样本的认知程度。GAN-AE 使用多个可控差异的重构子模型产生误差均值和方差，投票层把模型分歧转换为不确定性证据；低认知度或高不确定度不得直接产生橙/红告警，而应降级为疑似并进入特征仲裁。

**Blocked by:** 07, 08

**Status:** ready-for-agent

- [x] GAN-AE 至少装配 8 个可控差异的重构子模型，差异来源和数量可配置且可复现。
- [x] GAN-AE 返回重构误差均值、误差方差、归一化认知度和模型就绪状态。
- [x] 投票详情包含 `cognition`、`uncertainty`、`consensus_confidence`、各模型票和原始置信度。
- [x] 高不确定度或低认知度结果最多生成疑似黄色告警，并进入特征仲裁，不得直接升级为橙/红。
- [x] 认知度和置信度阈值可配置，模型故障或子模型不足时安全回退到现有三模型投票。
- [x] 告警详情保留不确定性证据，最近告警和时段查询可读取。
- [x] 覆盖正常、单票、双票、三票、高分歧、低认知度、子模型故障和阈值边界的测试。
- [x] VBA 基准报告优化前后准确率、误报率、召回率和置信度分布，确认门控没有降低主要指标。

## Comments

- 2026-11-01: Implemented eight configurable, reproducible GAN-AE reconstruction submodels with latent-rank/step/learning-rate/seed differences; ensemble mean/variance, cognition, uncertainty, readiness, submodel failures, and fallback evidence now flow through voting details. Low cognition/high uncertainty is capped at yellow suspected and now explicitly enters feature arbitration even when already anomalous, where the alert level remains capped. Added cognition/gating/alert-evidence tests and VBA traceability. Latest enhanced VBA report: accuracy 0.9706, FPR 0.0556, recall 1.0; 31 gated AI alerts and low-cognition/high-uncertainty bins both show 100% error concentration versus the 5.56% overall FPR.
