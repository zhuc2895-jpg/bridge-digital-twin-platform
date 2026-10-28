# 06: STALWART-inspired 与 Isolation Forest 检测器

**What to build:** 在统一检测器接口下实现两个可独立验证的异常检测模型：使用快慢 EMA 偏差识别突变的 STALWART-inspired 模型，以及使用滑动窗口训练真实孤立森林的 Isolation Forest 模型。两个模型都必须输出可用于投票和诊断的票、分数与置信度。

**Blocked by:** 05

**Status:** ready-for-agent

- [x] STALWART-inspired 模型维护快速 EMA（alpha=0.3）和慢速 EMA（alpha=0.05），以基线标准差归一化偏差；偏差超过 3 倍标准差时判定异常。
- [x] Isolation Forest 模型在每传感器滑动窗口上训练，支持可配置异常分数阈值，并在样本不足时安全返回“未就绪”而不是报错。
- [x] 两个模型对同一读数分别返回是否异常、异常分数、置信度和触发原因，模型参数与就绪状态可查询。
- [x] 正常稳态数据不触发异常；阶跃突变触发 STALWART-inspired；远离分布簇的离群点触发 Isolation Forest。
- [x] 模型单条推理不阻塞其他传感器，且有自动化测试覆盖样本不足、正常、突变、离群和参数变化。

## Comments

- 2026-10-28: Implemented STALWART-inspired fast/slow EMA and per-sensor sliding-window Isolation Forest detectors behind BaseDetector, including votes, scores, confidence, reasons, configurable parameters, independent readiness, safe insufficient-reading results, and automated coverage. Three-model voting remains scoped to issue 07.
- 2026-10-28: Calibrated Isolation Forest scores against each sensor's training distribution, added a zero-variance fallback, and added regression coverage for sustained normal readings, distant outliers, and cross-sensor readiness/inference.
