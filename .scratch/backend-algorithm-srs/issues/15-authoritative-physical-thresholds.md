# 15: 权威物理阈值与单位来源

**What to build:** 获取并应用权威的应变、位移、加速度、温度物理阈值，使系统不再依赖临时的代码默认值，并记录每条阈值配置的来源与版本。

**Blocked by:** 03, external engineering source

**Status:** needs-info

- [x] 提供权威 SRS、桥梁设计规范或经工程负责人签字的阈值表。
- [ ] 确认四类传感器阈值对应的单位和适用边界。
- [ ] 用权威值替换当前临时默认值，并更新配置、测试与文档。
- [x] 记录阈值来源、版本和生效日期，不把临时默认值宣称为正式限值。

## Information needed

- 权威文件或规范名称、版本和具体章节。
- 应变、位移、加速度、温度各自的黄/橙/红阈值及单位。
- 阈值是否适用于所有同类型传感器，或需要按传感器进一步区分。

## Comments

- 2026-11-01: Audited the project plan and repository records. They describe the intended threshold policy and provisional defaults but contain no authoritative SRS table, bridge-design clause, signed engineering threshold sheet, version, or effective date. The ticket remains `needs-info`; replacing the numeric defaults would fabricate provenance and is intentionally not done.
- 2026-11-01: Added the threshold provenance contract and API. Defaults are explicitly `provisional-default-v1` with no source/approver/effective date; `authoritative` requires document, version, section, ISO effective date, approving owner, scope, and all four unit labels. `GET /api/data/config/threshold-profile` and health expose the metadata, and runtime overrides cannot upgrade provenance. The remaining blocked items are still the external authoritative values, their confirmed units/scope, and replacing the provisional defaults. See ADR-0011.
- 2026-11-01: Added the TDD-driven single-document import seam `BRIDGE_THRESHOLD_PROFILE_PATH`. One JSON document now supplies both authoritative `thresholds` and `provenance`; individual threshold overrides are rejected when the document is active, preventing source/value divergence. The remaining blocker is still receipt of the actual external authoritative table.
- 2026-11-01: Extended the TDD guard so the single-document source also rejects a separate `BRIDGE_THRESHOLD_PROVENANCE_JSON`. Values and source metadata now have exactly one authoritative input path.
- 2026-11-01: Received and recorded the authoritative source catalogue in `docs/thresholds/authoritative-threshold-sources.md`: JT/T 1037-2022 §11/Table 9-10, SJG 148-2024 §8.3, MH/T 5088-2025 §9.3, JTG D60-2015, and JTG 3362-2018. The source confirms the yellow/orange/red mapping, units, and formulas. Remaining blockers are project-specific design basis values and engineering sign-off: historical maximum strain, design worst-case strain, design deflection for each displacement measurement, design temperature, the platform-defined red strain/temperature extrapolation, and per-measurement applicability. Without those, the profile remains `provisional-default-v1`.
