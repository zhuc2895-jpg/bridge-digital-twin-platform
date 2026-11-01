# 🌉 桥梁数字孪生健康监测平台

## Bridge Digital Twin Structural Health Monitoring Platform

> 工程场景数字化赛项参赛项目 | 数字孪生 + 桥梁结构健康监测与预警系统

---

## 📋 项目概述

针对我国公路桥梁超90万座、传统人工巡检效率低漏检率高的工程痛点，构建基于数字孪生的大跨径桥梁结构健康监测与智能预警平台。

### 核心KPI
- 异常检测响应时间：**天级 → 分钟级**
- 关键构件应力/位移预测准确率：**≥90%**
- 减少不必要实地巡检频次：**30%+**

---

## 🧠 三层递进式异常检测架构

```
传感器数据流
    │
    ▼
┌─────────────────────────────────────────────┐
│  第一层：快速筛查（统计+规则）                  │
│  smart-bridge-monitoring 引擎                │
│  → 物理阈值 + Top-K峰值 + 滚动窗口统计        │
│  → 耗时 <1ms，过滤90%正常数据                 │
└──────────────────┬──────────────────────────┘
                   │ 可疑数据
    ▼
┌─────────────────────────────────────────────┐
│  第二层：深度学习双模型投票                     │
│  ┌──────────────┐  ┌──────────────────────┐  │
│  │ STALWART     │  │ Hybrid GAN+AE        │  │
│  │ LSTM+RF+IF   │  │ 重构误差+分布偏差     │  │
│  │ 有监督/半监督  │  │ 无监督（只需正常数据） │  │
│  └──────┬───────┘  └──────────┬───────────┘  │
│         └─────────┬───────────┘              │
│              ┌────┴────┐                     │
│          一致异常    分歧                      │
│           →告警      →第三层                  │
└──────────────────┬──────────────────────────┘
                   │ 分歧样本
    ▼
┌─────────────────────────────────────────────┐
│  第三层：特征工程仲裁                          │
│  → 128维特征工程（ts-anomaly-detection）       │
│  → 多传感器交叉验证 + 历史趋势比对             │
└─────────────────────────────────────────────┘
```

---

## 🏗️ 技术架构

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **前端3D** | Vue3 + Three.js + ECharts + Pinia | 数字孪生可视化 |
| **后端** | FastAPI + WebSocket + NumPy | 实时数据推送 |
| **AI检测** | STALWART + Hybrid GAN+AE | 双模型深度学习 |
| **数据引擎** | smart-bridge-monitoring | O(1)查找 + 滚动窗口 |
| **BIM模型** | Revit → glTF 2.0 + Draco | 轻量化3D模型 |

---

## 📁 项目结构

```text
bridge-digital-twin-platform/
├── backend/
│   ├── app/
│   │   ├── api/                 # REST 路由
│   │   ├── engine/              # 数据引擎与仿真器
│   │   ├── ml/                  # 检测器、基线与投票
│   │   └── ws/                  # WebSocket 管理
│   ├── tests/                   # 后端自动化测试
│   └── requirements.txt
├── frontend/
│   ├── public/models/           # 浏览器加载的 glTF 模型
│   └── src/                     # Vue 组件、状态与数据访问
├── benchmarks/vba/              # VBA 损伤识别验收基准
├── data/
│   ├── samples/                 # 示例导入数据
│   ├── validation/              # 可提交的验证数据
│   ├── calibration/             # 版本化仿真-实测标定夹具
│   ├── modal/                   # 版本化模态与全场测点数据
│   └── external/                # 外部原始数据，默认不提交
├── assets/
│   ├── design/                  # BIM/Revit 源文件
│   ├── planning/                # 项目计划书等交付物
│   └── screenshots/             # 演示与验收截图
├── scripts/
│   ├── data/                    # 数据生成与导入工具
│   ├── docs/                    # 文档生成工具
│   └── dev/                     # 本地联调辅助脚本
├── docs/
│   ├── adr/                     # 架构决策记录
│   └── agents/                  # Agent 工作流配置
├── .scratch/                    # 本地 Markdown issue tracker
├── AGENTS.md
├── CONTEXT.md
├── start_backend.bat
├── start_frontend.bat
└── pyproject.toml
```

### 目录职责

- `backend/`、`frontend/`：可部署的应用源码，不存放临时验证文件。
- `data/`：按“示例、验证、外部原始数据”分级；`data/external/` 不进入 Git。
- `assets/`：非运行时二进制、设计源文件、交付文档和截图。
- `scripts/`：一次性或半自动工具；默认路径均从仓库根目录推导。
- `docs/`、`.scratch/`：决策记录、领域词汇和任务跟踪，不混入业务代码。

## 🧪 自动化测试

后端要求 Python 3.11+（本次验收使用 Python 3.13.7）。在仓库根目录执行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

依赖版本固定在 `backend/requirements.txt`；每个测试都会通过 `create_app()` 创建独立应用和独立状态存储，测试之间不共享传感器、告警或仿真器状态。

批量摄入接口：

- `POST /api/data/upload/json?push_live=true`：JSON 数组，最多 10000 条。
- `POST /api/data/upload/csv?push_live=true`：UTF-8 CSV，最多 10000 条。
- 每条记录必须包含 `sensor_id`、`name`、`type`、`value`、`timestamp`；类型仅支持 `strain`、`displacement`、`acceleration`、`temperature`。
- 整批数据会先完整校验再写入；任一记录非法时返回 400，且不会产生部分写入。

运行状态默认持久化到 `data/state/monitoring.json`。批次处理、阈值修改和正常停止都会提交原子检查点；进程重启后自动恢复最近一次完整检查点。损坏或不完整的检查点只会记录告警并被忽略，不阻止服务启动。存储通过 `CheckpointStore` 适配接口替换。

### 运行配置

所有运行参数通过统一 `AppConfig` 读取，默认值安全可用；部署时使用环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BRIDGE_HOST` / `BRIDGE_PORT` | `0.0.0.0` / `8000` | 直接运行入口的监听地址 |
| `BRIDGE_CHECKPOINT_PATH` | `data/state/monitoring.json` | 原子检查点位置 |
| `BRIDGE_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` |
| `BRIDGE_CORS_ORIGINS` | 本地 Vite 地址 | 逗号分隔的来源白名单，禁止 `*` |
| `BRIDGE_SIMULATION_ENABLED` | `true` | 关闭后不自动启动仿真或接受手动注入 |
| `BRIDGE_LIVE_INTERVAL_SECONDS` | `1.0` | Live Tick 周期 |
| `BRIDGE_AI_CONFIDENCE_THRESHOLD` / `BRIDGE_AI_MIN_VOTES` | `0.7` / `2` | AI 投票门槛 |
| `BRIDGE_FEATURE_MEAN_SHIFT_THRESHOLD` / `BRIDGE_FEATURE_VARIANCE_THRESHOLD` / `BRIDGE_FEATURE_TREND_THRESHOLD` | `2.0` / `2.0` / `2.0` | 第三层仲裁门槛 |
| `BRIDGE_GAN_SUBMODELS` | `8` | GAN-AE 重构子模型数量（不得少于 8） |
| `BRIDGE_COGNITION_THRESHOLD` / `BRIDGE_UNCERTAINTY_THRESHOLD` | `0.35` / `0.45` | 认知度门控阈值 |
| `BRIDGE_SPATIAL_RESIDUAL_THRESHOLD` | `3.0` | 跨传感器标准化残差阈值 |
| `BRIDGE_SPATIAL_MIN_TRAINING_SNAPSHOTS` / `BRIDGE_SPATIAL_MIN_SENSORS` / `BRIDGE_SPATIAL_MIN_COHERENT_SENSORS` | `30` / `3` / `2` | 空间模型训练与协同判定 |
| `BRIDGE_SPATIAL_ALPHA` / `BRIDGE_SPATIAL_WEIGHTS` | `0.001` / `{}` | 空间岭回归正则化与传感器权重 JSON |
| `BRIDGE_THRESHOLD_PROVENANCE_JSON` | 空（代码推导的待签值） | 阈值来源 JSON；权威来源必须含文档、版本、章节、生效日期和批准人 |
| `BRIDGE_THRESHOLD_PROFILE_PATH` | 空 | 单一权威阈值文档 JSON；含 `thresholds`、可选 `sensor_thresholds` 和 `provenance`，不可与单值阈值或独立来源 JSON 同时使用 |
| `BRIDGE_{TYPE}_{LEVEL}` | 见代码默认值 | 类型级物理阈值，例如 `BRIDGE_STRAIN_YELLOW=960` |

请求日志只记录方法、路径、状态、耗时和请求 ID，响应通过 `X-Request-ID` 返回同一标识。未处理异常返回稳定的 `INTERNAL_ERROR` 结构，不向客户端暴露堆栈。

物理阈值默认实现为代码中的 S01–S08 映射，版本 `competition-design-basis-v1`（`provisional`），定位为竞赛演示与算法验收基线，不会被宣称为正式限值；`config/bridge-threshold-profile.json` 是同一组值的版本化镜像，由测试保证内容一致。`GET /api/data/config/threshold-profile` 返回当前阈值、来源状态、文档/版本/章节、生效日期、批准人、适用范围和单位；只有完整权威元数据才能标记为 `authoritative`。

权威规范依据与公式整理见 `docs/thresholds/authoritative-threshold-sources.md`，本桥设计基准与 S01–S08 推导见 `docs/thresholds/sensor-baseline-and-mapping.md`。当前档案是竞赛可运行基线；面向后续 toB 部署时，只需在同一 JSON 中填写 `approved_by`、`effective_date` 并把 `status` 改为 `authoritative`，即可通过 `BRIDGE_THRESHOLD_PROFILE_PATH` 作为正式限值加载，数值无需改动。

设置任一 `BRIDGE_{TYPE}_{LEVEL}` 或调用 `POST /api/data/config/thresholds` 会切换到类型级整定模式，清除默认的逐测点覆盖并把 provenance 降级为 `provisional-default-v1`，避免 S01–S08 的映射把该调整静默屏蔽或把整定值伪装成设计基准。S08 当前只表达高温上限；低温与梯度温度报警需在设计基准补齐后增加。

### 系统验收入口

在仓库根目录执行完整验收入口：

```powershell
.\.venv\Scripts\python.exe -m benchmarks.acceptance
```

该命令依次运行全量 pytest、10,000 条批量摄入、常规查询、快照、三层 AI 单条检测、50+ QPS API 负载、10 个 WebSocket 客户端的 1Hz 推送，以及版本化验证数据集准确率/误报率门槛。结果写入 `benchmarks/runs/<UTC 时间>/acceptance.json` 与 `acceptance.md`；任一门槛失败时进程返回非零退出码。

24 小时稳定性入口：

```powershell
.\.venv\Scripts\python.exe -m benchmarks.stability --hours 24 --probe-interval 60 --clients 10
```

该入口持续记录工作集内存、WebSocket 连接数、实时帧吞吐、告警数、错误数和最终存活状态，报告写入 `benchmarks/stability/runs/`。无参数默认就是 24 小时；短时烟雾测试可传 `--hours 0.01`。

验证数据集清单为 `benchmarks/validation/manifest.json`，锁定生成脚本、随机种子、SHA-256、标签口径和门槛。报告明确标注数据为合成夹具；真实工程精度必须使用有限元模态与现场标定数据另行验收。

### VBA 融合验收

```powershell
.\.venv\Scripts\python.exe -m benchmarks.vba.evaluate --mode enhanced
```

冻结基线位于 `benchmarks/vba/baseline-v1.json`，增强报告写入 `benchmarks/vba/enhanced-v1.json` 与同名 Markdown。报告同时给出原始告警链路指标、融合分类指标、逐录音/逐折/逐工况结果、认知度与空间残差校准、门控与孤立残差抑制计数、推理耗时、内存变化、组件检查和失败回退。合成补偿/全场反演证据与真实 VBA 结果分栏，不混为一个精度结论。

### 响应与全场变形 API

- `POST /api/analysis/response-estimate`：仿真基础预测 + 实测补偿，返回预测、方差、可靠性、越域标记和物理阈值回退原因。
- `POST /api/analysis/deformation-inversion`：按能量选模、方向置信度加权和正则化求解模态坐标，返回全场变形、重建应变、残差与反演可信度；传入 `timestamp` 时关联当前或历史传感器快照。

### 容器部署

```bash
docker compose up --build
```

容器暴露 `http://localhost:8000` 与 `ws://localhost:8000/ws/live`，检查点通过 `bridge-state` 卷持久化到 `/app/data/state/monitoring.json`。CORS 来源、仿真开关、日志级别等均通过环境变量覆盖。

---

## 🚀 快速启动

### 后端
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
pnpm install
pnpm dev
```

访问 http://localhost:5173 即可看到平台界面。

---

## 📊 系统功能

- ✅ **3D桥梁数字孪生** — 旋转/缩放/点击构件查看详情
- ✅ **实时数据看板** — 8个传感器实时曲线
- ✅ **构件健康着色** — 绿→黄→橙→红四级预警
- ✅ **AI智能预警** — 三层递进检测，双模型交叉验证
- ✅ **历史回放** — 任意传感器任意时段数据回溯
- ✅ **数据仿真** — 内置仿真器，无需真实传感器
- ✅ **手动异常注入** — 一键触发异常演示

---

## 🔗 参考开源项目

| 项目 | 用途 | 链接 |
|------|------|------|
| TwinForge | 前端3D引擎框架 | [GitHub](https://github.com/XinCodingBreeze/TwinForge) |
| smart-bridge-monitoring | 数据引擎 | [GitHub](https://github.com/nathademola/smart-bridge-monitoring) |
| STALWART | 主检测器 | [GitHub](https://github.com/gitdeeper4/stalwart) |
| Hybrid GAN+AE | 辅助检测器 | [GitHub](https://github.com/aditya-m-mishra/Hybrid-anomaly-detection-using-GAN-and-auto-encoders) |
| ts-anomaly-detection | 特征工程 | [GitHub](https://github.com/Vaishnav-M/ts-anomaly-detection) |
| bridge_twin | 完整参考 | [GitHub](https://github.com/neel-09/bridge_twin) |

---

## 📅 开发时间线

| 阶段 | 时间 | 任务 |
|------|------|------|
| 选题调研 | 2026.9-10 | 文献综述、需求分析、方案设计 |
| 原型开发 | 2026.11-12 | 核心功能实现、模型训练 |
| 功能完善 | 2027.1-2 | 前后端联调、性能优化 |
| 任务命题文档 | 2027.3上旬 | 撰写提交 |
| 赛前打磨 | 2027.3中下旬 | 演示优化、答辩准备 |

---

## 👥 团队

| 角色 | 专业 | 职责 |
|------|------|------|
| 队长 | 土木工程 | 工程分析、系统设计、项目管理 |
| 前端/可视化 | 计算机/软件 | Three.js、Vue3、ECharts |
| 算法/后端 | 计算机/AI | FastAPI、深度学习模型 |
| 机动（可选） | 美工/UI | 界面设计、答辩PPT |
