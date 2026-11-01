# 19: 多方向应变模态与全场变形反演

**What to build:** 借鉴多方向数字孪生应变场和模态叠加方法，根据模态能量选择主导模态，以传感器可信度加权求解模态坐标，再叠加位移模态得到全场变形。反演结果同时返回重建应变、变形场、反演残差和可信度，使结构状态从单点告警扩展为全场状态证据。

**Blocked by:** 04, 18

**Status:** ready-for-agent

- [x] 支持从版本化模态数据中按能量贡献率选择主导模态，并记录截断依据。
- [x] 低信噪比或验证质量不足的应变方向可降权或剔除，不与其他方向等权。
- [x] 使用传感器可信度权重和正则化求解模态坐标，避免传感器稀疏或共线时数值失稳。
- [x] 输出全场变形、模态坐标、重建应变、实测与重建残差以及反演可信度。
- [x] 提供指定时间点的变形反演接口，结果可关联当前和历史传感器快照。
- [x] 使用已知模态的合成夹具验证重建 `R²`、`RRMSE`、变形误差和模态选择行为。
- [x] 覆盖模态不足、方向缺失、低信噪比、传感器故障、病态矩阵和越界时间点的测试。
- [x] 文档明确合成夹具通过不代表真实桥梁精度；真实精度需使用有限元模态和实测变形另行验收。

## Comments

- 2026-11-01: Added versioned synthetic modal data with orthogonal multi-direction strain/displacement bases, energy-based mode truncation, SNR/confidence filtering, weighted ridge inversion, condition diagnostics, full-field output, and `POST /api/analysis/deformation-inversion` with retained snapshot linking and timestamp bounds. Eight tests cover contract round-trip, mode selection, coordinate/displacement recovery (R² > 0.99, RRMSE < 0.01), low SNR/confidence, missing direction, sensor fault, insufficient measurements, ill-conditioned modes, and API snapshot linkage. Synthetic results are explicitly separated from real finite-element acceptance.
