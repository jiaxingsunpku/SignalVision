# SignalVision

基于强化学习的交通信号控制（Traffic Signal Control, TSC）系统，包含一个 **LibSignal 训练/仿真内核** 与一套 **Web 可视化控制台**。支持在 SUMO / CityFlow 等仿真器上训练、评估多种信控算法，并通过浏览器实时观测路网、路口相位与拥堵状态。

---

## 目录

- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [目录结构](#目录结构)
- [环境准备](#环境准备)
- [快速开始](#快速开始)
  - [运行训练 / 评估](#1-运行训练--评估runtime)
  - [启动可视化控制台](#2-启动可视化控制台dashboard)
- [配置系统](#配置系统)
- [支持的算法与场景](#支持的算法与场景)
- [子模块文档](#子模块文档)
- [常见问题](#常见问题)

---

## 核心特性

- **多算法**：内置 12+ 种信控算法，涵盖强化学习（CoLight、MPLight、PressLight、FRAP、DQN、PPO、SAC、MADDPG、MAGD）与规则方法（MaxPressure、FixedTime、SOTL）。
- **多仿真器**：默认 **SUMO**（`libsumo` 快速接口 / `traci` 标准接口），同时兼容 **CityFlow** 与 **OpenEngine**。
- **注册表驱动**：核心组件（task / trainer / world / agent / dataset）通过 `Registry` 装饰器注册，运行时按名字查表装配，扩展只需新增一个文件 + 一份配置。
- **解耦的适配层**：Dashboard 依赖抽象 `StandardInterface`，而非具体框架，更换训练后端无需改前端。
- **Web 控制台**：Flask 后端 + 原生前端，提供路网渲染、路口相位查看/编辑、仿真启停、实时数据、模型/实验管理等 REST API。
- **丰富的数据集**：内置 Manhattan、Hangzhou、Cologne、Ingolstadt、NewYork、合成网格等数十个标准路网场景。

---

## 系统架构

```
┌──────────────────────────────────────────────┐
│  Dashboard 前端 (templates / static)          │  浏览器
│  路网渲染 · 路口面板 · 仿真控制 · 工具栏        │
└───────────────────────┬──────────────────────┘
                        │ REST API (Flask)
┌───────────────────────▼──────────────────────┐
│  dashboard/  (server.py · simulation_manager) │  Web 服务
│  integration/ 实时集成 · dashboard_tools/ 工具 │
└───────────────────────┬──────────────────────┘
                        │ 调用标准接口
┌───────────────────────▼──────────────────────┐
│  adapter/  标准接口 + LibSignal 适配器          │  解耦桥梁
│  StandardInterface ←→ LibSignalAdapter         │
└───────────────────────┬──────────────────────┘
                        │ 驱动训练内核
┌───────────────────────▼──────────────────────┐
│  runtime/  (LibSignal 内核)                    │  计算核心
│  task → trainer(runner) → world + agent        │
│  Registry 注册表统一装配                        │
└───────────────────────┬──────────────────────┘
                        │
┌───────────────────────▼──────────────────────┐
│  SUMO / CityFlow / OpenEngine 仿真器           │  底层仿真
└──────────────────────────────────────────────┘
```

调用链：**前端 → Dashboard → Adapter（标准接口）→ Runtime（LibSignal）→ 仿真器**。

---

## 目录结构

```
SignalVision/
├── runtime/                  # 训练 / 仿真内核（LibSignal）
│   ├── run.py                # 训练 / 评估入口
│   ├── environment.py        # TSCEnv 环境封装
│   ├── agent/                # 信控算法（colight / dqn / frap / mplight / ppo ...）
│   ├── world/                # 仿真器后端（sumo / cityflow / openengine）
│   ├── task/                 # 任务编排（TSCTask）
│   ├── runner/               # 训练循环（TSCRunner.train / test）
│   ├── generator/            # 状态 / 观测生成器
│   ├── dataset/              # 在线采样数据集（onfly）
│   ├── common/               # 基础设施（registry / metrics / interface / converter）
│   ├── utils/                # 日志、配置构建（build_config）、相位查表
│   ├── configs/
│   │   ├── tsc/              # 算法配置 *.yml（含 base.yml）
│   │   └── sim/              # 场景配置 *.cfg
│   ├── data/raw_data/        # 路网 + 流量数据集（81 / manhattan / hangzhou ...）
│   └── tools/                # 流量反演、拥堵流生成、OD、可视化等离线工具
│
├── adapter/                  # Dashboard ↔ Runtime 适配层
│   ├── standard_interface.py # 抽象接口（StandardArgs / Simulation / Solver / Interface）
│   ├── libsignal_adapter.py  # LibSignal 具体实现
│   ├── config_converter.py   # 配置 / 算法名 / 场景名映射
│   └── network_data_loader.py# 路网数据加载与缓存
│
├── dashboard/                # Flask Web 控制台
│   ├── server.py             # 主服务（~50 个 REST 路由）
│   ├── simulation_manager.py # 仿真生命周期管理（集成 / 子进程两种模式）
│   ├── simulation_config.py  # 配置与预设管理
│   ├── config.json           # 服务器 / 地图 / TDengine 等配置
│   ├── integration/          # SUMO 实时集成（junction_agent / interface / controller）
│   ├── dashboard_tools/      # 离线工具（数据 / 模型 / 对比实验，部分为占位）
│   ├── templates/ static/    # 前端页面与资源
│   └── experiments/          # 对比实验输出
│
└── cache/                    # 路网数据缓存
    └── <map>/netdata.pkl     # 各地图的预解析路网（ezhou / guanggu / output ...）
```

---

## 环境准备

### 1. SUMO（系统依赖）

SUMO 是默认仿真器，必须先安装并设置 `SUMO_HOME`：

```bash
# Ubuntu 示例
sudo apt install sumo sumo-tools sumo-doc
export SUMO_HOME=/usr/share/sumo
```

`libsumo` / `traci` / `sumolib` 均由 SUMO 提供。若使用 CityFlow 后端，需另行安装 CityFlow。

### 2. Python 依赖

建议 Python 3.8+，使用虚拟环境。仓库内 `runtime/requirements.txt` **不完整**（仅列出部分基础包），完整依赖如下：

```bash
# 训练内核
pip install torch numpy==1.21.5 gym==0.21.0 pyyaml lmdb sympy mpmath
pip install pfrl torch_geometric torch_scatter        # RL / 图网络算法
pip install matplotlib seaborn pandas scipy networkx tqdm

# Dashboard
pip install flask flask_cors
```

> 注：部分算法依赖 `tensorflow`；`torch_geometric` / `torch_scatter` 需与本机 PyTorch / CUDA 版本匹配。

---

## 快速开始

### 1. 运行训练 / 评估（runtime）

> **重要：必须在 `runtime/` 目录下运行**，因为 `run.py` 以相对导入和相对路径加载配置。

```bash
cd runtime

# 评估 MaxPressure（规则算法，无需训练）在 81 场景上
python run.py -a maxpressure -n 81 -w sumo

# 训练 CoLight（RL）在 hangzhou 4x4 场景上
python run.py -a colight_pytorch_agent -n sumohz4x4 -w sumo
```

主要命令行参数（详见 [run.py](runtime/run.py)）：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-a, --agent` | 算法 → 加载 `configs/tsc/<agent>.yml` | `colight_pytorch_agent` |
| `-n, --network` | 场景 → 加载 `configs/sim/<network>.cfg` | `ezhou` |
| `-w, --world` | 仿真器：`sumo` / `cityflow` | `sumo` |
| `-t, --task` | 任务类型 | `tsc` |
| `-d, --dataset` | 数据集类型 | `onfly` |
| `--interface` | `libsumo`（快）/ `traci`（慢，可视化） | `libsumo` |
| `--ngpu` | 使用的 GPU 卡号 | `0` |
| `--prefix` | 本次运行输出前缀 | `test` |

是否训练 / 测试由算法 yml 中的 `model.train_model` / `model.test_model` 控制。

### 2. 启动可视化控制台（dashboard）

```bash
cd dashboard
python server.py --port 8080 --map 81
```

启动后访问 `http://localhost:8080`。常用参数：

| 参数 | 说明 | 默认值（来自 config.json） |
|------|------|------|
| `--host` | 监听地址 | `0.0.0.0` |
| `--port` | 端口 | `8080` |
| `--map` | 默认地图（覆盖 config.json） | `guanggu` |
| `--debug` | 调试模式 | `false` |
| `--config` | 指定配置文件路径 | `dashboard/config.json` |

服务器配置（端口、默认地图、TDengine 等）见 [dashboard/config.json](dashboard/config.json)。

---

## 配置系统

训练运行需要 **两份配置**，由 `runtime/utils/logger.py` 的 `build_config()` 合并：

1. **算法配置** `configs/tsc/<agent>.yml`
   通过 `includes:` 继承 [base.yml](runtime/configs/tsc/base.yml)，覆盖 `model` / `trainer` / `logger` 等字段。

   ```yaml
   includes:
     - configs/tsc/base.yml
   model:
     name: maxpressure
     train_model: False
     test_model: True
   trainer:
     action_interval: 10
   ```

2. **场景配置** `configs/sim/<network>.cfg`（JSON 格式）
   指定路网 / 流量文件路径，由 `common/interface.py` 按 `network` 名解析。

   ```json
   {
     "network": "81",
     "combined_file": "raw_data/81/81.sumocfg",
     "roadnetFile": "raw_data/81/81.net.xml",
     "flowFile": "raw_data/81/81.rou.xml"
   }
   ```

Dashboard 侧配置与场景/算法名映射由 [adapter/config_converter.py](adapter/config_converter.py) 处理（如 `81 ↔ sumo81`、`maxpressure ↔ maxpressure_agent`）。

---

## 支持的算法与场景

**算法**（`runtime/agent/`，配置在 `runtime/configs/tsc/`）：

| 类型 | 算法 |
|------|------|
| 强化学习 | CoLight、MPLight、PressLight、FRAP、DQN、PPO、SAC、MADDPG、MAGD |
| 规则方法 | MaxPressure、FixedTime、SOTL |

**场景**（`runtime/configs/sim/` + `runtime/data/raw_data/`）：
`81`、`manhattan_28x7`、`hangzhou_*`、`cologne1/3`、`ingolstadt21`、`NewYork`、`arterial_1x6`、`syn_*`（合成网格）等数十个。

---

## 子模块文档

- [adapter/README.md](adapter/README.md) — 适配层设计与扩展指南
- [dashboard/dashboard_tools/README.md](dashboard/dashboard_tools/README.md) — Dashboard 工具模块 API
- [runtime/tools/README_FLOW_INVERTER.md](runtime/tools/README_FLOW_INVERTER.md) — 流量反演工具

---

## 常见问题

**Q：`python run.py` 报找不到模块 / 配置文件？**
A：务必在 `runtime/` 目录下运行。`run.py` 使用相对导入（`import task`、`import agent`）和相对路径（`./configs/...`）。

**Q：SUMO 相关导入失败（`libsumo` / `traci`）？**
A：确认已安装 SUMO 并设置 `SUMO_HOME`。可用 `--interface traci` 切换到标准接口便于调试可视化。

**Q：`requirements.txt` 装完仍缺包？**
A：该文件不完整，请参考上文[环境准备](#2-python-依赖)安装完整依赖。

**Q：项目暂无 git 提交历史？**
A：当前为代码快照，`dashboard/dashboard_tools/` 中部分功能（训练/数据/模型/对比实验）仍为占位实现，详见其 README。
