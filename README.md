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

```
bridge-digital-twin-platform/
├── frontend/                          # Vue3 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── BridgeViewer.vue       # 3D桥梁查看器（核心）
│   │   │   ├── DataDashboard.vue      # 实时数据仪表盘
│   │   │   ├── AlertPanel.vue         # 智能预警面板
│   │   │   ├── HistoryPlayback.vue    # 历史回放
│   │   │   └── SensorMarker.vue       # 传感器标注组件
│   │   ├── composables/
│   │   │   ├── useWebSocket.ts        # WebSocket实时连接
│   │   │   └── useSensorData.ts       # 传感器数据管理
│   │   ├── stores/
│   │   │   └── bridgeStore.ts         # Pinia全局状态
│   │   ├── views/
│   │   │   └── MainPlatform.vue       # 主平台页面
│   │   ├── App.vue
│   │   └── main.ts
│   ├── public/models/                 # 3D模型文件
│   │   └── bridge.glb                 # 桥梁glTF模型（待获取）
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── backend/                           # FastAPI 后端
│   ├── app/
│   │   ├── main.py                    # 入口 + WebSocket
│   │   ├── api/
│   │   │   ├── routes_sensor.py       # 传感器数据API
│   │   │   ├── routes_alert.py        # 告警管理API
│   │   │   └── routes_analysis.py     # 数据分析API
│   │   ├── engine/
│   │   │   ├── data_engine.py         # 数据引擎
│   │   │   └── simulator.py           # 数据仿真器
│   │   ├── ml/
│   │   │   └── anomaly_detector.py    # 三层异常检测
│   │   └── ws/
│   │       └── websocket_manager.py   # WebSocket管理
│   └── requirements.txt
│
└── README.md
```

---

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
