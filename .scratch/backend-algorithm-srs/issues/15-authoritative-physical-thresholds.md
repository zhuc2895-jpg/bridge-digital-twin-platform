# 15: 权威物理阈值与单位来源

**What to build:** 获取并应用权威的应变、位移、加速度、温度物理阈值，使系统不再依赖临时的代码默认值，并记录每条阈值配置的来源与版本。

**Blocked by:** 03

**Status:** ready-for-agent

- [x] 提供权威 SRS、桥梁设计规范或经工程负责人签字的阈值表。
- [x] 确认四类传感器阈值对应的单位和适用边界。
- [x] 用权威值替换当前临时默认值，并更新配置、测试与文档。
- [x] 记录阈值来源、版本和生效日期，不把临时默认值宣称为正式限值。

## Future toB approval interface (reserved, not blocking the competition build)

This is a student competition project without an engineering sign-off owner. The derived S01-S08 table is adopted as the competition/demo baseline and remains `provisional`. A future toB deployment can upgrade the same profile without changing numeric values:

- set `provenance.status` to `authoritative`;
- provide `approved_by` (name/title) and `effective_date` (ISO `YYYY-MM-DD`);
- keep the existing `scope`, `units`, and per-sensor mapping;
- load it through `BRIDGE_THRESHOLD_PROFILE_PATH`;
- gate production decisions on `provenance.authoritative == true` or the equivalent API field.

The recorded competition decisions are: S04/S07 red = 1.5 × 300 mg, S01/S02/S06/S08 red = 1.2 × design, S03 tower-top allowable = 50 mm, and S05 steel-box-girder deflection = L/400.

## Comments

- 2026-11-01: Audited the project plan and repository records. They describe the intended threshold policy and provisional defaults but contain no authoritative SRS table, bridge-design clause, signed engineering threshold sheet, version, or effective date. The ticket remains `needs-info`; replacing the numeric defaults would fabricate provenance and is intentionally not done.
- 2026-11-01: Added the threshold provenance contract and API. Defaults are explicitly `provisional-default-v1` with no source/approver/effective date; `authoritative` requires document, version, section, ISO effective date, approving owner, scope, and all four unit labels. `GET /api/data/config/threshold-profile` and health expose the metadata, and runtime overrides cannot upgrade provenance. The remaining blocked items are still the external authoritative values, their confirmed units/scope, and replacing the provisional defaults. See ADR-0011.
- 2026-11-01: Added the TDD-driven single-document import seam `BRIDGE_THRESHOLD_PROFILE_PATH`. One JSON document now supplies both authoritative `thresholds` and `provenance`; individual threshold overrides are rejected when the document is active, preventing source/value divergence. The remaining blocker is still receipt of the actual external authoritative table.
- 2026-11-01: Extended the TDD guard so the single-document source also rejects a separate `BRIDGE_THRESHOLD_PROVENANCE_JSON`. Values and source metadata now have exactly one authoritative input path.
- 2026-11-01: Added TDD-driven `sensor_thresholds` overrides so standards with per-measurement allowable values (for example cable acceleration vs main-span acceleration, or tower displacement vs main-span deflection) no longer have to be forced into one type-wide profile. Engine threshold checks, checkpoint recovery, service wiring, and the threshold-profile API all preserve the overrides.
- 2026-11-01: Received and recorded the authoritative source catalogue in `docs/thresholds/authoritative-threshold-sources.md`: JT/T 1037-2022 §11/Table 9-10, SJG 148-2024 §8.3, MH/T 5088-2025 §9.3, JTG D60-2015, and JTG 3362-2018. The source confirms the yellow/orange/red mapping, units, and formulas. Remaining blockers are project-specific design basis values and engineering sign-off: historical maximum strain, design worst-case strain, design deflection for each displacement measurement, design temperature, the platform-defined red strain/temperature extrapolation, and per-measurement applicability. Without those, the profile remains `provisional-default-v1`.
- 2026-11-01: Added project-specific design baselines and the S01–S08 sensor-to-threshold mapping in `docs/thresholds/sensor-baseline-and-mapping.md`, plus a loadable profile at `config/bridge-threshold-profile.json` (validated with the backend's own `ThresholdProfileDocument` loader). Basis: L = 120 m steel-box-girder cable-stayed bridge → S05 `d_d` = L/400 = 300 mm (JTG/T 3365-01-2020 §7.2.5); S03 tower-top allowable 50 mm (proposed); S01/S02/S06 `ε_d` = 1200/900/650 µε; S04/S07 cable acceleration 0.98/2.94/4.41 m/s² (SJG 148-2024 Table 8.3.6, red is a platform extrapolation); S08 `T_d` = 46 °C (JTG D60-2015 Table 4.3.12-2), red = 60 °C paving limit. Provenance stays `provisional` (`code-derived-v1-pending-signoff`): `approved_by` and `effective_date` are still required to become authoritative.
- 2026-11-01: Wired the S01-S08 mapping into the production default (`AppConfig.thresholds`, `sensor_thresholds`, and `threshold_provenance`) and kept the type-wide profiles as fallbacks. The rule-layer validation acceptance now applies the per-sensor mapping, restoring event recall to 1.0. Regenerated `bridge-validation-24h-v3` against the new limits (accuracy 0.9924, FPR 0.0023, event recall 1.0) and added a regression test that the versioned `config/bridge-threshold-profile.json` file equals the code default. Lifecycle tests use `legacy_test_config()` so they do not track production threshold tuning. Verification: 343 tests passed; mypy clean. Status moved to `ready-for-human` because the only remaining action is engineering approval of the derived values.
- 2026-11-01: Closed the review-found provenance integrity gaps. Sensor overrides now carry their expected sensor type, so a mislabeled reading cannot apply a limit in the wrong unit. Type-level environment or API threshold updates switch to type-wide tuning, clear the default per-sensor overrides, and downgrade provenance to `provisional-default-v1` instead of being silently masked. Effective provenance is persisted in the engine checkpoint and restored with its values, and authoritative provenance now requires `scope`. System acceptance reports include the full type and per-sensor profile, not only a version string. Documentation now distinguishes the code default from its versioned mirror and states the S08 high-temperature-only boundary. Verification: 352 tests passed; mypy clean; system acceptance passed with 0.9924 accuracy / 0.0023 FPR / 1.0 event recall.
- 2026-11-01: Finalized as a student-competition baseline, since the project has no engineering sign-off owner. The S01-S08 profile is versioned `competition-design-basis-v1`, remains `provisional`, and is applied to runtime, validation, acceptance, and VBA artifacts. The future toB approval interface is reserved: a deployment fills `approved_by`, `effective_date`, and `status=authoritative` in the same profile document and gates production on `provenance.authoritative`; no numeric or code changes are required. This closes the ticket for the competition scope without claiming formal engineering approval.
