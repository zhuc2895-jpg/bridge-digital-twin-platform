# 11: HTML 监测报告

**What to build:** 提供可直接在浏览器查看和打印为 PDF 的 HTML 监测报告。报告按指定统计时段汇总监测概况、传感器状态、最近 50 条告警和系统运行状态，所有数字与实时存储中的数据一致。

**Blocked by:** 03, 04

**Status:** ready-for-agent

- [x] 报告接口接受 `hours` 参数，默认 24，仅允许 1～168，非法值返回 400。
- [x] 报告包含在线传感器数、累计读数、红/橙/黄告警统计、各传感器最新读数与状态、最近 50 条告警和系统运行状态。
- [x] 告警按时间倒序展示，统计时段与请求参数一致；无告警时给出明确空状态。
- [x] 页面包含打印按钮和打印样式，浏览器打印预览中不显示仅屏幕使用的控件。
- [x] 标题、传感器名称和告警消息等动态内容经过 HTML 转义，报告不执行注入内容。
- [x] 覆盖默认时段、边界时段、非法时段、无数据、告警截断和内容准确性测试。

## Comments

- 2026-11-01: Implemented the report as a dedicated renderer in `app/html_report.py`. The endpoint now uses the exact requested trailing period, reports current latest-reading thresholds as sensor status, truncates the alert table to the newest 50 while retaining full period counts, escapes all dynamic text, and returns 400 for invalid `hours`. Verification: targeted report suite 13 passed; full backend suite 237 passed; mypy and targeted Ruff passed.
