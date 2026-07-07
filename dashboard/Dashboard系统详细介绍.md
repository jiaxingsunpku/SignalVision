# Dashboard 交通监控与管理平台 - 系统详细介绍

## 目录

- [1. 系统概述](#1-系统概述)
- [2. 系统架构](#2-系统架构)
- [3. 核心模块](#3-核心模块)
- [4. 数据流与工作流程](#4-数据流与工作流程)
- [5. API接口规范](#5-api接口规范)
- [6. 集成模式](#6-集成模式)
- [7. 配置管理](#7-配置管理)
- [8. 部署与使用](#8-部署与使用)

---

## 1. 系统概述

Dashboard是一个通用的交通监控与管理Web平台，为智能交通信号控制系统提供可视化监控、数据分析、模型管理和实验对比等功能。系统采用前后端分离架构，不依赖特定的仿真器或算法，具有良好的扩展性和灵活性。

### 1.1 核心特性

- **实时监控**：路网状态实时展示、交通流动态可视化
- **通用接入**：不绑定SUMO，支持任意仿真器/实际系统接入
- **功能完整**：涵盖监控、训练、测试、分析全流程
- **易于扩展**：模块化设计，插件化工具系统
- **专业可靠**：RESTful API，完善的错误处理

### 1.2 技术栈

| 层级 | 技术选型 |
|------|---------|
| **后端框架** | Flask (Python Web框架) |
| **跨域支持** | Flask-CORS |
| **时序数据库** | TDengine (可选) |
| **前端技术** | HTML5/CSS3/JavaScript |
| **可视化** | Canvas/SVG |
| **仿真集成** | SUMO (通过LibSUMO/TraCI) |

### 1.3 应用场景

- **交通管理部门**：实时监控、应急响应、效果评估
- **科研机构**：算法研究、性能对比、数据采集
- **高校教学**：教学演示、学生实验、课程项目

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层 (Frontend)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  地图可视化   │  │  实时监控面板 │  │  工具模块界面 │          │
│  │   Canvas     │  │   Statistics │  │   Training   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                          ↕ HTTP/REST API                         │
└─────────────────────────────────────────────────────────────────┘
                                ↕
┌─────────────────────────────────────────────────────────────────┐
│                      后端服务层 (Backend)                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    server.py (Flask)                       │ │
│  │  - API路由管理  - 请求处理  - 错误处理  - 日志记录         │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                ↕                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │  Integration     │  │  Dashboard Tools │  │   Config      │ │
│  │  集成模块        │  │  工具模块        │  │   配置模块     │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                ↕
┌─────────────────────────────────────────────────────────────────┐
│                      数据与仿真层 (Data)                         │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  SUMO仿真    │  │  TDengine    │  │  模型文件    │          │
│  │   (LibSUMO)  │  │   时序数据库  │  │   (PKL/PTH)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 模块架构

```
dashboard/
├── server.py                    # 主服务器入口
├── start.sh                     # 启动脚本
├── config.json                  # 主配置文件
├── inference_config.json        # 推理模式配置
│
├── integration/                 # 集成模块（核心）
│   ├── junction_agent.py        # 路口智能体
│   ├── dashboard_controller.py  # 仿真控制器
│   └── dashboard_interface.py   # 接口适配器
│
├── dashboard_tools/             # 工具模块（功能扩展）
│   ├── training_controller.py   # 训练管理
│   ├── realtime_traffic_data_controller.py  # 实时交通数据
│   ├── models_controller.py     # 模型管理
│   └── continual_learning_controller.py # 持续学习
│
├── simulation_manager.py        # 仿真管理器
├── simulation_config.py         # 仿真配置生成器
│
├── templates/                   # HTML模板
│   └── index.html              # 主页面
│
└── static/                      # 静态资源
    ├── css/                     # 样式文件
    ├── js/                      # JavaScript脚本
    └── html/                    # 其他HTML页面
```

### 2.3 层次关系：单控制器 - 多智能体架构

Dashboard采用**单个中央控制器协调多个路口智能体**的分层架构，实现人机协同与多系统接入。

```
┌────────────────────────────────────────────────────────────────┐
│                    人机交互层 (Human-Computer Interaction)      │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │ Web前端界面  │  │  REST API    │  │  人工干预接口      │   │
│  │ (可视化监控) │  │  (程序调用)  │  │  (手动控制)        │   │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬─────────┘   │
│         │                 │                     │             │
│         └─────────────────┴─────────────────────┘             │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTP/WebSocket
                               ↓
┌────────────────────────────────────────────────────────────────┐
│              中央控制器层 (Single Central Controller)           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              SimulationManager (进程管理器)               │ │
│  │  - 管理仿真进程生命周期                                    │ │
│  │  - 统一调度与资源分配                                      │ │
│  │  - 全局状态监控                                           │ │
│  └─────────────────────┬────────────────────────────────────┘ │
│                        │                                       │
│  ┌─────────────────────▼────────────────────────────────────┐ │
│  │          DashboardController (核心控制器)                │ │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │ │
│  │  【单一实例 - 全局协调】                                  │ │
│  │  - 初始化和配置所有组件                                   │ │
│  │  - 同步协调多个路口智能体                                 │ │
│  │  - 处理全局决策和优化                                     │ │
│  │  - 聚合数据向上层报告                                     │ │
│  └─────────────────────┬────────────────────────────────────┘ │
└────────────────────────┼─────────────────────────────────────┘
                         │ 协调指令/数据聚合
                         ↓
┌────────────────────────────────────────────────────────────────┐
│           多智能体层 (Multi-Agent Layer)                        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              JunctionManager (智能体管理器)              │ │
│  │  - 维护所有路口智能体实例                                 │ │
│  │  - 批量数据分发与收集                                     │ │
│  │  - 智能体间协作协调                                       │ │
│  └─────────────┬────────────────────────────────────────────┘ │
│                │                                               │
│  ┌─────────────▼────────────────────────────────────────────┐ │
│  │             路口智能体集群 (Junction Agents)             │ │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │ │
│  │  【多实例 - 分布式自治】                                 │ │
│  │                                                           │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│  │  │ JunctionAgent│  │ JunctionAgent│  │ JunctionAgent│     │ │
│  │  │   路口 J1    │  │   路口 J2    │  │   路口 J3    │     │ │
│  │  │  ─────────  │  │  ─────────  │  │  ─────────  │     │ │
│  │  │ · 状态感知   │  │ · 状态感知   │  │ · 状态感知   │  ··· │ │
│  │  │ · 指标计算   │  │ · 指标计算   │  │ · 指标计算   │     │ │
│  │  │ · 本地决策   │  │ · 本地决策   │  │ · 本地决策   │     │ │
│  │  │ · 邻居协调   │  │ · 邻居协调   │  │ · 邻居协调   │     │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │ │
│  │                                                           │ │
│  │         每个智能体独立管理一个路口                         │ │
│  │         路口数量：可扩展至数百个                          │ │
│  └───────────────────────────────────────────────────────────┘ │
└────────────────────────┬─────────────────────────────────────┘
                         │ 数据订阅/控制指令
                         ↓
┌────────────────────────────────────────────────────────────────┐
│            底层接入层 (Infrastructure Integration)              │
│                                                                 │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │  交通仿真API    │  │   数据存储层     │  │  外部系统API  │ │
│  │  ━━━━━━━━━━━   │  │   ━━━━━━━━━━    │  │  ━━━━━━━━━  │ │
│  │                 │  │                  │  │              │ │
│  │  ┌───────────┐ │  │  ┌────────────┐ │  │ ┌──────────┐ │ │
│  │  │   SUMO    │ │  │  │ TDengine   │ │  │ │ 交管系统  │ │
│  │  │ 仿真器     │ │  │  │ 时序数据库  │ │  │ │ (REST)   │ │
│  │  └───────────┘ │  │  └────────────┘ │  │ └──────────┘ │ │
│  │                 │  │                  │  │              │ │
│  │  ┌───────────┐ │  │  ┌────────────┐ │  │ ┌──────────┐ │ │
│  │  │  VISSIM   │ │  │  │ PostgreSQL │ │  │ │检测器系统 │ │
│  │  │ (可扩展)   │ │  │  │ (可扩展)   │ │  │ │(可扩展)  │ │
│  │  └───────────┘ │  │  └────────────┘ │  │ └──────────┘ │ │
│  │                 │  │                  │  │              │ │
│  │  ┌───────────┐ │  │  ┌────────────┐ │  │ ┌──────────┐ │ │
│  │  │ CityFlow  │ │  │  │   Redis    │ │  │ │信号机系统 │ │
│  │  │ (可扩展)   │ │  │  │ (可扩展)   │ │  │ │(可扩展)  │ │
│  │  └───────────┘ │  │  └────────────┘ │  │ └──────────┘ │ │
│  │                 │  │                  │  │              │ │
│  │ · LibSUMO/TraCI│  │ · 时序数据存储   │  │ · HTTP/MQTT │ │
│  │ · 仿真控制接口  │  │ · 历史数据查询   │  │ · 实时数据推送│ │
│  │ · 可插拔设计    │  │ · 数据分析支持   │  │ · 双向控制   │ │
│  └─────────────────┘  └──────────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

### 2.3.1 架构特点说明

#### 🎯 单一中央控制器 (Single Central Controller)

**DashboardController** 是整个系统的核心，作为**唯一的全局协调者**：

- **单例模式**：全系统仅有一个控制器实例
- **全局视角**：掌握所有路口的完整信息
- **统一调度**：协调所有智能体的行为
- **策略制定**：实施全局优化策略
- **状态聚合**：汇总数据向上层报告

**职责边界**：
```
✓ 初始化系统        ✓ 管理仿真生命周期
✓ 全局配置          ✓ 资源分配
✓ 智能体协调        ✓ 数据聚合
✗ 不处理单路口细节  ✗ 不直接操作底层API
```

#### 🤖 多路口智能体 (Multiple Junction Agents)

**JunctionAgent** 是分布式自治的路口管理单元，**数量与路口数相等**（可达数百个）：

- **自治性**：每个智能体独立管理一个路口
- **本地决策**：基于本地状态快速响应
- **邻居协调**：与相邻路口智能体通信
- **状态维护**：实时跟踪车道、信号灯、车辆
- **指标计算**：本地计算拥堵度等性能指标

**智能体特性**：
```
✓ 实例数 = 路口数   ✓ 独立状态空间
✓ 本地实时计算      ✓ 邻居通信
✓ 故障隔离          ✓ 可动态增删
```

#### 🔄 数据流向

**向上流动**（智能体 → 控制器 → 前端）：
```
单个路口数据 → 智能体处理 → JunctionManager聚合 → 
DashboardController整合 → REST API → 前端展示/人工决策
```

**向下流动**（前端 → 控制器 → 智能体）：
```
人工指令 → REST API → DashboardController解析 → 
分发到目标智能体 → 执行控制 → 反馈结果
```

#### 🔌 底层接入的灵活性

Dashboard设计为**接口无关**，可接入任何交通数据源：

**仿真系统接入**：
- SUMO（已实现）：通过LibSUMO/TraCI
- VISSIM（可扩展）：通过COM接口
- CityFlow（可扩展）：通过Python API
- 任意自定义仿真器：实现标准接口

**实际系统接入**：
- 交通管理平台：HTTP/REST API
- 检测器系统：MQTT推送
- 信号机系统：工业协议（如GB/T）
- 视频分析系统：实时数据流

**数据存储接入**：
- TDengine：时序数据（已集成）
- PostgreSQL/MySQL：关系数据
- Redis：缓存和实时状态
- InfluxDB/TimescaleDB：时序数据（可选）

#### 📊 架构优势

| 优势 | 说明 | 收益 |
|------|------|------|
| **单点协调** | 中央控制器统一调度 | 全局最优、避免冲突 |
| **分布式处理** | 智能体并行计算 | 高性能、可扩展 |
| **故障隔离** | 单个智能体故障不影响全局 | 高可靠性 |
| **灵活接入** | 标准化接口适配多种系统 | 通用性强 |
| **人机协同** | 支持自动+人工干预 | 实用性强 |

#### 🔧 扩展示例

**添加新的仿真器**：
```python
# 1. 实现仿真器适配器
class VISSIMAdapter:
    def get_junction_data(self, junction_id):
        # 从VISSIM获取路口数据
        return vissim_data
    
    def set_signal_phase(self, junction_id, phase):
        # 设置VISSIM信号灯相位
        vissim.set_phase(junction_id, phase)

# 2. 注册到DashboardController
controller.register_simulator('vissim', VISSIMAdapter())

# 3. JunctionAgent自动适配
# 无需修改智能体代码，数据流自动切换
```

**接入实际交管系统**：
```python
# 外部系统推送实时数据
@app.route('/api/junctions/<id>/update', methods=['POST'])
def update_from_traffic_system(id):
    data = request.json
    
    # 更新对应的JunctionAgent
    agent = junction_manager.get_junction(id)
    agent.update_lane_data(...)
    
    return {'success': True}
```

### 2.3.2 与传统架构对比

| 维度 | 传统单体架构 | Dashboard架构 |
|------|-------------|--------------|
| **控制器** | 多个控制器独立运行 | 单一中央控制器 |
| **路口管理** | 集中式或完全独立 | 智能体自治+全局协调 |
| **扩展性** | 受限于单机性能 | 可水平扩展至数百路口 |
| **接入方式** | 紧耦合特定系统 | 松耦合标准接口 |
| **人机交互** | 命令行或专用客户端 | 通用Web界面+API |
| **故障处理** | 单点故障影响全局 | 智能体级别故障隔离 |

---

## 3. 核心模块

### 3.1 Integration 集成模块

集成模块负责将SUMO仿真系统与Dashboard平台无缝连接。

#### 3.1.1 JunctionAgent (路口智能体)

**职责**：
- 维护单个路口的静态信息（位置、车道、拓扑）
- 接收和存储实时交通状态
- 计算路口性能指标
- 提供查询接口供前端显示

**核心数据结构**：

```python
@dataclass
class LaneInfo:
    """车道信息"""
    lane_id: str              # 车道ID
    direction: str            # 'incoming' / 'outgoing'
    length: float             # 车道长度
    speed_limit: float        # 限速
    vehicle_count: int        # 实时车辆数
    mean_speed: float         # 平均速度
    occupancy: float          # 占有率
    halting_count: int        # 停车数

@dataclass
class TrafficLightState:
    """交通信号灯状态"""
    phase_state: str          # 相位状态串 "rrrGGGrrrGGG"
    phase_duration: float     # 相位持续时间
    next_switch_time: float   # 下次切换时间
    actual_duration: int      # 实际持续时间

@dataclass
class JunctionMetrics:
    """路口性能指标"""
    total_vehicles: int       # 总车辆数
    average_speed: float      # 平均速度
    average_occupancy: float  # 平均占有率
    total_halting: int        # 停车总数
    congestion_level: float   # 拥堵级别 (0-1)
```

**关键方法**：

```python
class JunctionAgent:
    def add_lane(lane_id, direction, length, speed_limit)
        # 添加车道信息
    
    def update_lane_data(lane_id, vehicle_count, mean_speed, 
                        occupancy, halting_count)
        # 更新车道实时数据
    
    def update_traffic_light(phase_state, phase_duration, 
                            next_switch_time, actual_duration)
        # 更新交通信号灯状态
    
    def calculate_metrics()
        # 计算路口性能指标（拥堵级别等）
    
    def get_state_dict() -> Dict
        # 获取完整状态（供API返回）
    
    def get_summary() -> Dict
        # 获取摘要信息（供地图显示）
```

**拥堵级别计算算法**：

```python
if total_vehicles < 5:
    congestion_level = 0.0  # 车辆少，视为顺畅
else:
    # 速度因子 (50%)
    speed_factor = 1.0 - min(average_speed / speed_limit, 1.0)
    
    # 车辆数因子 (25%)
    vehicle_factor = min(total_vehicles / (lane_count * 15), 1.0)
    
    # 停车因子 (25%)
    halting_factor = min(total_halting / (lane_count * 8), 1.0)
    
    # 综合拥堵度
    congestion_level = (speed_factor * 0.5 + 
                       vehicle_factor * 0.25 + 
                       halting_factor * 0.25)
```

#### 3.1.2 JunctionManager (路口管理器)

**职责**：
- 管理所有JunctionAgent实例
- 提供统一的访问接口
- 批量更新所有路口指标

**核心方法**：

```python
class JunctionManager:
    def initialize_from_network_data(network_data)
        # 从网络数据初始化所有路口
    
    def get_junction(junction_id) -> JunctionAgent
        # 获取指定路口
    
    def get_all_summaries() -> List[Dict]
        # 获取所有路口摘要信息
    
    def update_all_metrics()
        # 批量更新所有路口指标
    
    def reset_all()
        # 重置所有路口状态
```

#### 3.1.3 DashboardController (仿真控制器)

**职责**：
- 初始化和管理SUMO仿真
- 初始化和管理智能体系统
- 协调数据流：SUMO → JunctionAgent → 前端
- 协调决策流：JunctionAgent → 智能体 → SUMO

**初始化流程**：

```
1. 解析命令行参数
   └─> args = parse_cl_args()

2. 创建SUMO仿真实例
   └─> simulation = SumoSim(args)

3. 创建智能体系统
   └─> solver = pposolver(args)  或
       solver = maxpressuresolver(args)

4. 生成仿真环境
   └─> simulation.gen_sim()

5. 创建Dashboard接口
   └─> interface = DashboardInterface(sim, sys, junction_manager)

6. 连接各组件
   └─> simulation.set_interface(interface)
   └─> solver.set_interface(interface)

7. 更新网络数据
   └─> simulation.update_netdata()

8. 初始化JunctionAgent
   └─> junction_manager.initialize_from_network_data(netdata)
```

**仿真步进流程**：

```python
def step():
    """执行一个仿真步骤"""
    # 1. 生成车辆
    vehiclegen.run()
    
    # 2. 更新通行时间统计
    update_travel_times()
    
    # 3. 信号决策（智能体）
    interface.signal_update()
    
    # 4. SUMO执行一步
    simulation.sim_step()
    
    # 5. 更新JunctionAgent数据
    _update_junction_agents()
    
    # 6. 步骤延迟（如果设置）
    time.sleep(step_delay)
    
    # 7. 返回当前状态
    return get_current_state()
```

**数据更新流程**：

```python
def _update_junction_agents():
    """从订阅缓存更新JunctionAgent"""
    # 获取订阅缓存
    subscription_cache = interface.subscription_cache
    
    # 更新车道数据
    for lane_id, data in subscription_cache['lane_data'].items():
        junction_id = find_junction_for_lane(lane_id)
        junction = junction_manager.get_junction(junction_id)
        junction.update_lane_data(
            lane_id, vehicle_count, mean_speed, occupancy, halting_count
        )
    
    # 更新交通信号灯数据
    for tl_id, data in subscription_cache['traffic_light_data'].items():
        junction = junction_manager.get_junction(tl_id)
        junction.update_traffic_light(
            phase_state, phase_duration, next_switch_time, actual_duration
        )
    
    # 批量计算指标
    junction_manager.update_all_metrics()
```

#### 3.1.4 DashboardInterface (接口适配器)

**职责**：
- 连接SUMO仿真和智能体系统
- 缓存订阅数据供JunctionAgent使用
- 处理信号更新和决策

**数据缓存结构**：

```python
subscription_cache = {
    'lane_data': {
        'lane_id_1': {
            'vehicle_number': int,
            'mean_speed': float,
            'occupancy': float,
            'halting_number': int
        },
        ...
    },
    'traffic_light_data': {
        'tl_id_1': {
            'phase_state': str,
            'phase_duration': float,
            'next_switch': float,
            'actual_duration': int
        },
        ...
    }
}
```

### 3.2 Dashboard Tools 工具模块

工具模块提供离线任务功能，与实时仿真独立运行。

#### 3.2.1 TrainingController (训练管理)

**功能**：管理PPO模型的训练流程

**主要方法**：

```python
class TrainingController:
    def start_training(config):
        """
        启动训练任务
        Args:
            config: {
                'map_name': str,
                'epochs': int,
                'batch_size': int,
                'learning_rate': float,
                ...
            }
        Returns:
            {'success': bool, 'message': str, 'task_id': str}
        """
        
    def stop_training():
        """停止当前训练任务"""
        
    def get_training_status():
        """
        获取训练状态
        Returns:
            {
                'running': bool,
                'current_epoch': int,
                'total_epochs': int,
                'loss': float,
                'metrics': {...}
            }
        """
        
    def get_training_logs(limit=100):
        """获取最近的训练日志"""
```

**API端点**：
- `POST /api/tools/training/start` - 启动训练
- `POST /api/tools/training/stop` - 停止训练
- `GET /api/tools/training/status` - 获取状态
- `GET /api/tools/training/logs` - 获取日志

#### 3.2.2 DataController (数据管理)

**功能**：管理交通数据的查询、分析和导出

**数据源**：TDengine时序数据库

**主要方法**：

```python
class DataController:
    def __init__(self, tdengine_host, tdengine_port):
        """连接TDengine数据库"""
        
    def query_data(query_params):
        """
        查询交通数据
        Args:
            query_params: {
                'start_time': str,
                'end_time': str,
                'junction_ids': List[str],
                'data_type': str  # 'vehicle' / 'lane' / 'signal'
            }
        Returns:
            {'success': bool, 'data': [...]}
        """
        
    def analyze_data(analysis_params):
        """
        分析交通数据
        Args:
            analysis_params: {
                'data': [...],
                'analysis_type': str  # 'trend' / 'distribution' / 'correlation'
            }
        Returns:
            {'success': bool, 'results': {...}}
        """
        
    def export_data(export_params):
        """
        导出数据
        Args:
            export_params: {
                'data': [...],
                'format': str  # 'csv' / 'json' / 'excel'
            }
        Returns:
            {'success': bool, 'file_path': str}
        """
        
    def get_data_statistics():
        """获取数据统计信息（总量、时间范围等）"""
```

**API端点**：
- `POST /api/tools/data/query` - 查询数据
- `POST /api/tools/data/analyze` - 分析数据
- `POST /api/tools/data/export` - 导出数据
- `GET /api/tools/data/statistics` - 获取统计

#### 3.2.3 ModelsController (模型管理)

**功能**：管理PPO模型的存储、加载和版本控制

**模型目录结构**：

```
log/
└── ppo/
    └── scenario_name/
        ├── weights/
        │   ├── epoch_100.pth
        │   ├── epoch_200.pth
        │   └── ...
        ├── checkpoint_epoch_100.pth
        ├── params.json
        └── metrics.png
```

**主要方法**：

```python
class ModelsController:
    def list_models(filters=None):
        """
        列出所有模型
        Args:
            filters: {
                'algorithm': str,  # 'ppo' / 'maxpressure'
                'scenario': str,
                'min_epoch': int
            }
        Returns:
            {
                'success': bool,
                'models': [
                    {
                        'model_id': str,
                        'algorithm': str,
                        'epoch': int,
                        'scenario': str,
                        'created_at': str
                    },
                    ...
                ]
            }
        """
        
    def load_model(model_id):
        """加载指定模型到内存"""
        
    def delete_model(model_id):
        """删除模型文件"""
        
    def get_model_info(model_id):
        """
        获取模型详细信息
        Returns:
            {
                'model_id': str,
                'params': {...},
                'metrics': {...},
                'file_size': int
            }
        """
        
    def evaluate_model(model_id, eval_params):
        """
        评估模型性能
        Args:
            eval_params: {
                'scenario': str,
                'simulation_length': int
            }
        """
```

**API端点**：
- `GET /api/tools/models/list` - 列出模型
- `POST /api/tools/models/load` - 加载模型
- `POST /api/tools/models/delete` - 删除模型
- `GET /api/tools/models/info/<model_id>` - 获取信息
- `POST /api/tools/models/evaluate` - 评估模型

#### 3.2.4 ComparisonController (对比实验)

**功能**：管理不同模型和算法的对比实验

**实验配置**：

```json
{
  "experiment_name": "PPO vs MaxPressure",
  "description": "对比PPO和MaxPressure在杭州4x4路网的性能",
  "scenarios": ["hangzhou_4x4"],
  "algorithms": [
    {
      "name": "ppo",
      "model_path": "log/ppo/scenario/checkpoint.pth"
    },
    {
      "name": "maxpressure"
    },
    {
      "name": "fixedtime"
    }
  ],
  "simulation_config": {
    "simulation_length": 3600,
    "replications": 5,
    "scale": 2
  },
  "metrics": [
    "avg_travel_time",
    "avg_speed",
    "avg_waiting_time",
    "queue_length"
  ]
}
```

**主要方法**：

```python
class ComparisonController:
    def create_experiment(experiment_config):
        """创建对比实验"""
        
    def run_experiment(experiment_id):
        """
        运行实验（后台线程）
        流程：
        1. 对每个场景
        2.   对每个算法
        3.     运行N次仿真
        4.     记录指标
        5. 汇总结果
        6. 计算统计显著性
        """
        
    def get_experiment_status(experiment_id):
        """
        获取实验状态
        Returns:
            {
                'running': bool,
                'progress': float,  # 0.0 - 1.0
                'current_task': str,
                'results': {...}  # 部分结果
            }
        """
        
    def get_experiment_results(experiment_id):
        """
        获取完整结果
        Returns:
            {
                'experiment_id': str,
                'algorithms': {
                    'ppo': {
                        'avg_travel_time': {
                            'mean': float,
                            'std': float,
                            'values': [...]
                        },
                        ...
                    },
                    'maxpressure': {...}
                },
                'comparison': {
                    'ppo_vs_maxpressure': {
                        'p_value': float,
                        'significant': bool
                    }
                }
            }
        """
        
    def generate_report(experiment_id, report_format='html'):
        """生成可视化报告"""
```

**API端点**：
- `POST /api/tools/comparison/create` - 创建实验
- `POST /api/tools/comparison/run` - 运行实验
- `GET /api/tools/comparison/status/<exp_id>` - 获取状态
- `GET /api/tools/comparison/results/<exp_id>` - 获取结果
- `POST /api/tools/comparison/report` - 生成报告

### 3.3 SimulationManager (仿真管理器)

**职责**：
- 管理仿真进程的生命周期
- 支持两种运行模式：集成模式、子进程模式
- 监控仿真状态和输出

**运行模式对比**：

| 特性 | 集成模式 | 子进程模式 |
|------|---------|-----------|
| **实现方式** | DashboardController内部 | 独立进程 |
| **数据同步** | 直接访问JunctionManager | API通信 |
| **性能** | 高（无进程切换） | 中（进程间通信） |
| **隔离性** | 低（同进程） | 高（独立进程） |
| **适用场景** | 深度集成 | 松耦合 |

**主要方法**：

```python
class SimulationManager:
    def start(config, sim_name, inference_mode, **kwargs):
        """
        启动仿真
        Args:
            config: 预设名称 ('maxpressure', 'ppo', ...)
            sim_name: 场景名称
            inference_mode: 推理模式
                - 'inference': 基础推理
                - 'inference_with_visualization': 带可视化
                - 'inference_quick': 快速测试
                - 'inference_full': 完整推理
                - 'inference_database': 数据库模式
        """
        
    def stop():
        """停止仿真"""
        
    def get_status():
        """
        获取仿真状态
        Returns:
            {
                'running': bool,
                'config': str,
                'current_time': int,
                'total_time': int,
                'pid': int,
                'mode': str  # 'integration' / 'subprocess'
            }
        """
        
    def get_junction_manager():
        """获取JunctionManager实例（仅集成模式）"""
```

### 3.4 SimulationConfig (配置生成器)

**职责**：
- 管理仿真预设配置
- 生成仿真启动命令
- 处理参数覆盖

**预设配置**：

```python
PRESETS = {
    'maxpressure': {
        'tsc': 'maxpressure',
        'mode': 'test',
        'nogui': True,
        'enable_db': False
    },
    'maxpressure_gui': {
        'tsc': 'maxpressure',
        'mode': 'test',
        'nogui': False,
        'enable_db': True
    },
    'ppo': {
        'tsc': 'ppo',
        'mode': 'test',
        'resume': True,
        'resume_path': 'log/ppo/...',
        'nogui': True,
        'enable_db': False
    },
    ...
}
```

**推理模式配置**（`inference_config.json`）：

```json
{
  "inference": {
    "nogui": true,
    "enable_db": false,
    "simlen": 3600,
    "scale": 10,
    "step_delay": 50
  },
  "inference_with_visualization": {
    "nogui": false,
    "enable_db": true,
    "simlen": 3600,
    "scale": 2,
    "step_delay": 1000
  },
  "inference_quick": {
    "nogui": true,
    "enable_db": false,
    "simlen": 1800,
    "scale": 1
  },
  ...
}
```

**命令生成流程**：

```
1. 加载默认参数 (DEFAULT_ARGS)
2. 应用推理配置 (inference_config.json)
3. 应用预设配置 (PRESETS)
4. 应用场景名称 (sim_name)
5. 应用用户覆盖 (kwargs)
6. 生成命令行参数列表
```

---

## 4. 数据流与工作流程

### 4.1 仿真启动流程

```
用户 → Web界面
  ↓ 点击"启动仿真"
前端 → POST /api/simulation/start
  ↓ {config: 'ppo', simlen: 3600}
server.py → start_simulation()
  ↓
SimulationManager.start()
  ↓
判断运行模式
  ├─ 集成模式 → DashboardController
  │    ├─ 初始化SUMO仿真
  │    ├─ 初始化智能体系统
  │    ├─ 创建JunctionManager
  │    └─ 在后台线程运行
  │
  └─ 子进程模式 → subprocess.Popen
       └─ 启动独立Python进程
```

### 4.2 实时数据流

```
SUMO仿真
  ↓ LibSUMO订阅
DashboardInterface
  ↓ 缓存订阅数据
DashboardController._update_junction_agents()
  ↓ 更新车道和信号灯数据
JunctionAgent
  ↓ 计算指标
JunctionManager
  ↓ API查询
前端 (轮询 /api/simulation/realtime)
  ↓
可视化展示
```

**详细数据流**：

```python
# 1. SUMO订阅数据
traci.lane.subscribe(lane_id, [
    tc.LAST_STEP_VEHICLE_NUMBER,
    tc.LAST_STEP_MEAN_SPEED,
    tc.LAST_STEP_OCCUPANCY,
    tc.LAST_STEP_HALTING_NUMBER
])

# 2. Interface缓存
subscription_cache = {
    'lane_data': traci.lane.getSubscriptionResults(),
    'traffic_light_data': traci.trafficlight.getSubscriptionResults()
}

# 3. JunctionAgent更新
for lane_id, data in subscription_cache['lane_data'].items():
    junction.update_lane_data(
        lane_id, 
        data[tc.LAST_STEP_VEHICLE_NUMBER],
        data[tc.LAST_STEP_MEAN_SPEED],
        data[tc.LAST_STEP_OCCUPANCY],
        data[tc.LAST_STEP_HALTING_NUMBER]
    )

# 4. 计算指标
junction.calculate_metrics()

# 5. API返回
return {
    'junctions': junction_manager.get_all_summaries()
}
```

### 4.3 决策控制流

```
仿真步进
  ↓
DashboardInterface.signal_update()
  ↓
遍历所有路口
  ↓ 对每个路口
获取状态 (get_state)
  ↓
智能体决策 (solver.update)
  ├─ PPO → 神经网络推理
  ├─ MaxPressure → 压力计算
  └─ FixedTime → 固定周期
  ↓
应用动作 (set_phase)
  ↓
SUMO执行
```

### 4.4 完整工作流程

```
┌────────────────────────────────────────┐
│  1. 用户启动仿真                        │
│     POST /api/simulation/start         │
└───────────────┬────────────────────────┘
                │
┌───────────────▼────────────────────────┐
│  2. SimulationManager创建              │
│     DashboardController                │
└───────────────┬────────────────────────┘
                │
┌───────────────▼────────────────────────┐
│  3. 初始化组件                          │
│     - SUMO仿真                         │
│     - 智能体系统                        │
│     - JunctionManager                  │
└───────────────┬────────────────────────┘
                │
┌───────────────▼────────────────────────┐
│  4. 仿真循环 (每步)                     │
│   ┌──────────────────────────┐        │
│   │ a. 生成车辆               │        │
│   └────┬─────────────────────┘        │
│   ┌────▼─────────────────────┐        │
│   │ b. 智能体决策             │        │
│   └────┬─────────────────────┘        │
│   ┌────▼─────────────────────┐        │
│   │ c. SUMO执行一步           │        │
│   └────┬─────────────────────┘        │
│   ┌────▼─────────────────────┐        │
│   │ d. 更新JunctionAgent      │        │
│   └────┬─────────────────────┘        │
│   ┌────▼─────────────────────┐        │
│   │ e. 延迟（如果设置）        │        │
│   └──────────────────────────┘        │
└───────────────┬────────────────────────┘
                │
┌───────────────▼────────────────────────┐
│  5. 前端轮询 (每秒)                     │
│     GET /api/simulation/realtime       │
└───────────────┬────────────────────────┘
                │
┌───────────────▼────────────────────────┐
│  6. 前端更新显示                        │
│     - 地图可视化                        │
│     - 统计面板                          │
│     - 拥堵热力图                        │
└────────────────────────────────────────┘
```

---

## 5. API接口规范

### 5.1 通用响应格式

**成功响应**：
```json
{
  "success": true,
  "data": {...},
  "message": "操作成功"
}
```

**失败响应**：
```json
{
  "success": false,
  "error": "错误描述",
  "message": "用户友好的错误信息"
}
```

### 5.2 核心API

#### 5.2.1 配置API

**获取前端配置**
```
GET /api/config
Response: {
  "config": {
    "dashboard": {...},
    "map": {...}
  },
  "success": true
}
```

#### 5.2.2 网络数据API

**获取网络数据**
```
GET /api/network
Response: {
  "network_data": {
    "inter": {...},
    "lane": {...},
    "edge": {...}
  },
  "junction_count": 81,
  "success": true
}
```

#### 5.2.3 路口API

**获取所有路口摘要**
```
GET /api/junctions/summary
Response: {
  "summaries": [
    {
      "junction_id": "J13",
      "position": [x, y],
      "congestion_level": 0.3,
      "total_vehicles": 8,
      "phase_type": "green"
    },
    ...
  ],
  "count": 81,
  "success": true
}
```

**获取路口详情**
```
GET /api/junctions/<junction_id>
Response: {
  "junction": {
    "junction_id": "J13",
    "position": [x, y],
    "incoming_lanes": {...},
    "outgoing_lanes": {...},
    "traffic_light": {...},
    "metrics": {...}
  },
  "success": true
}
```

**更新路口数据**（供外部系统调用）
```
POST /api/junctions/<junction_id>/update
Body: {
  "lane_data": {...},
  "traffic_light": {...}
}
Response: {
  "success": true,
  "message": "路口数据已更新"
}
```

#### 5.2.4 仿真控制API

**启动仿真**
```
POST /api/simulation/start
Body: {
  "config": "ppo",          // 预设名称
  "sim_name": "81",         // 场景名称（可选）
  "simlen": 3600,           // 覆盖参数（可选）
  "scale": 2
}
Response: {
  "success": true,
  "message": "仿真启动成功",
  "pid": 12345
}
```

**停止仿真**
```
POST /api/simulation/stop
Response: {
  "success": true,
  "message": "仿真已停止"
}
```

**获取仿真状态**
```
GET /api/simulation/status
Response: {
  "running": true,
  "config": "ppo",
  "current_time": 1500,
  "total_time": 3600,
  "pid": 12345,
  "mode": "integration"
}
```

**获取实时数据**
```
GET /api/simulation/realtime
Response: {
  "success": true,
  "simulation": {
    "running": true,
    "current_time": 1500,
    "config": "ppo"
  },
  "statistics": {
    "total_vehicles": 156,
    "avg_speed": 8.5,
    "total_waiting": 32,
    "active_junctions": 81
  },
  "junctions": [...]
}
```

**获取仿真输出**
```
GET /api/simulation/output?lines=20
Response: {
  "output": [
    "Step #100/3600",
    "Vehicles: 50",
    ...
  ]
}
```

**获取预设列表**
```
GET /api/simulation/presets
Response: {
  "presets": [
    {
      "name": "maxpressure",
      "description": "MaxPressure算法测试",
      "tsc": "maxpressure",
      "mode": "test"
    },
    ...
  ],
  "current_map": "81"
}
```

#### 5.2.5 地图管理API

**列出可用地图**
```
GET /api/maps
Response: {
  "maps": [
    {
      "name": "81/netdata.pkl",
      "path": "81/netdata.pkl",
      "size": 1048576
    },
    ...
  ],
  "count": 5,
  "success": true
}
```

**加载地图**
```
POST /api/load-map
Body: {
  "map_path": "81/netdata.pkl"
}
Response: {
  "success": true,
  "message": "地图加载成功",
  "junction_count": 81
}
```

### 5.3 工具模块API

#### 训练管理
```
POST   /api/tools/training/start       # 启动训练
POST   /api/tools/training/stop        # 停止训练
GET    /api/tools/training/status      # 获取状态
GET    /api/tools/training/logs        # 获取日志
```

#### 数据管理
```
POST   /api/tools/data/query           # 查询数据
POST   /api/tools/data/analyze         # 分析数据
POST   /api/tools/data/export          # 导出数据
GET    /api/tools/data/statistics      # 获取统计
GET    /api/tools/data/tdengine-config # 获取数据库配置
```

#### 模型管理
```
GET    /api/tools/models/list          # 列出模型
POST   /api/tools/models/load          # 加载模型
POST   /api/tools/models/delete        # 删除模型
GET    /api/tools/models/info/<id>     # 获取模型信息
POST   /api/tools/models/evaluate      # 评估模型
GET    /api/tools/models/file/<id>/<type> # 获取模型文件
```

#### 对比实验
```
POST   /api/tools/comparison/start     # 启动实验
POST   /api/tools/comparison/create    # 创建实验
POST   /api/tools/comparison/run       # 运行实验
POST   /api/tools/comparison/stop      # 停止实验
GET    /api/tools/comparison/status/<id>  # 获取状态
GET    /api/tools/comparison/results/<id> # 获取结果
GET    /api/tools/comparison/list      # 列出实验
GET    /api/tools/comparison/export/<id>  # 导出结果
POST   /api/tools/comparison/report    # 生成报告
```

---

## 6. 集成模式

### 6.1 集成模式 vs 子进程模式

#### 集成模式（推荐）

**特点**：
- DashboardController直接管理SUMO和智能体
- JunctionManager在同一进程中
- 数据访问无延迟
- 适用于深度集成场景

**优势**：
- ✅ 性能最优（无进程间通信开销）
- ✅ 数据同步实时
- ✅ 调试方便
- ✅ 代码简洁

**劣势**：
- ❌ 隔离性较差
- ❌ 仿真崩溃影响Dashboard

**启用方式**：
```python
# simulation_manager.py
self.use_integration = True  # 默认启用
```

#### 子进程模式

**特点**：
- 仿真在独立进程运行
- 通过API通信
- 进程隔离

**优势**：
- ✅ 隔离性好
- ✅ 仿真崩溃不影响Dashboard
- ✅ 适用于松耦合场景

**劣势**：
- ❌ 性能较低（进程间通信）
- ❌ 数据同步有延迟
- ❌ 实现复杂

**启用方式**：
```python
# simulation_manager.py
self.use_integration = False
```

### 6.2 接入其他仿真器

Dashboard设计为仿真器无关，可以接入任何仿真平台。

**接入步骤**：

1. **实现JunctionAgent接口**

```python
class CustomJunctionAgent(JunctionAgent):
    def update_from_custom_sim(self, sim_data):
        """从自定义仿真器更新数据"""
        # 解析仿真器数据
        for lane_id, lane_data in sim_data.items():
            self.update_lane_data(
                lane_id,
                lane_data['vehicle_count'],
                lane_data['mean_speed'],
                lane_data['occupancy'],
                lane_data['halting_count']
            )
```

2. **创建仿真控制器**

```python
class CustomSimulationController:
    def __init__(self, junction_manager):
        self.junction_manager = junction_manager
        self.sim = YourSimulator()
    
    def step(self):
        # 执行仿真步骤
        self.sim.step()
        
        # 获取仿真数据
        sim_data = self.sim.get_data()
        
        # 更新JunctionAgent
        for junction_id, data in sim_data.items():
            junction = self.junction_manager.get_junction(junction_id)
            junction.update_from_custom_sim(data)
```

3. **注册到SimulationManager**

```python
# 修改 simulation_manager.py
def _start_custom_sim(self, config, **kwargs):
    controller = CustomSimulationController(self.junction_manager)
    # 运行仿真...
```

### 6.3 接入实际交通系统

Dashboard也可以接入实际的交通管理系统，用于实时监控。

**接入流程**：

```
实际交通系统
  ↓ 数据推送（HTTP/MQTT/WebSocket）
Dashboard API
  ↓ POST /api/junctions/<id>/update
JunctionAgent
  ↓ 更新状态
前端可视化
```

**实现示例**：

```python
# 外部系统推送数据
import requests

def push_traffic_data(junction_id, data):
    requests.post(
        f'http://dashboard:8080/api/junctions/{junction_id}/update',
        json={
            'lane_data': {
                'lane_1': {
                    'vehicle_count': 5,
                    'mean_speed': 8.5,
                    'occupancy': 0.3,
                    'halting_count': 2
                }
            },
            'traffic_light': {
                'phase_state': 'rrrGGGrrrGGG',
                'phase_duration': 30,
                'next_switch_time': 45
            }
        }
    )
```

---

## 7. 配置管理

### 7.1 config.json (主配置)

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8080,
    "debug": false
  },
  "map": {
    "directory": "cache",
    "default_map": "output",
    "netdata_filename": "netdata.pkl"
  },
  "dashboard": {
    "title": "交通信控系统",
    "auto_refresh": false,
    "refresh_interval": 5000,
    "default_view": {
      "show_edges": true,
      "show_junctions": true,
      "show_congestion": true,
      "line_width": 2,
      "node_size": 6
    }
  },
  "api": {
    "enable_cors": true,
    "max_history_size": 100
  },
  "tdengine": {
    "host": "localhost",
    "port": 6060
  }
}
```

### 7.2 inference_config.json (推理模式配置)

定义了5种推理模式：

| 模式 | 描述 | GUI | 数据库 | 时长 | 延迟 |
|------|------|-----|-------|------|------|
| `inference` | 默认推理 | ❌ | ❌ | 3600s | 50ms |
| `inference_with_visualization` | 带可视化 | ✅ | ✅ | 3600s | 1000ms |
| `inference_quick` | 快速测试 | ❌ | ❌ | 1800s | 0ms |
| `inference_full` | 完整推理 | ❌ | ✅ | 7200s | 0ms |
| `inference_database` | 数据库模式 | ❌ | ✅ | 3600s | 500ms |

**使用场景**：

- **inference**: 普通推理，适合快速查看效果
- **inference_with_visualization**: 演示、教学，需要观察仿真过程
- **inference_quick**: 快速验证算法逻辑
- **inference_full**: 完整性能评估
- **inference_database**: 数据采集，用于后续分析

---

## 8. 部署与使用

### 8.1 快速开始

#### 安装依赖

```bash
pip install flask flask-cors
```

#### 启动服务

```bash
cd dashboard
bash start.sh
```

或手动启动：

```bash
python server.py --host 0.0.0.0 --port 8080 --map 81
```

#### 访问界面

打开浏览器访问：`http://localhost:8080`

### 8.2 使用流程

#### 1. 启动仿真

**方式1：Web界面**
- 访问Dashboard
- 点击"启动仿真"按钮
- 选择算法和参数
- 点击确认

**方式2：API调用**
```bash
curl -X POST http://localhost:8080/api/simulation/start \
  -H "Content-Type: application/json" \
  -d '{
    "config": "ppo",
    "simlen": 3600,
    "scale": 2
  }'
```

#### 2. 实时监控

前端自动轮询`/api/simulation/realtime`，每秒更新：
- 地图上路口的拥堵颜色
- 统计面板的指标
- 信号灯状态

#### 3. 查看详情

点击地图上的路口，显示详细信息：
- 车道数据
- 信号灯状态
- 性能指标

#### 4. 停止仿真

点击"停止仿真"按钮或调用API：
```bash
curl -X POST http://localhost:8080/api/simulation/stop
```

### 8.3 高级功能

#### 训练模型

```bash
curl -X POST http://localhost:8080/api/tools/training/start \
  -H "Content-Type: application/json" \
  -d '{
    "map_name": "81",
    "epochs": 100,
    "learning_rate": 0.0001
  }'
```

#### 对比实验

```bash
curl -X POST http://localhost:8080/api/tools/comparison/start \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_name": "PPO vs MaxPressure",
    "scenarios": ["81"],
    "algorithms": ["ppo", "maxpressure"],
    "simulation_length": 3600,
    "replications": 5
  }'
```

#### 数据分析

```bash
curl -X POST http://localhost:8080/api/tools/data/query \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-01-01 00:00:00",
    "end_time": "2024-01-01 01:00:00",
    "junction_ids": ["J13", "J14"]
  }'
```

### 8.4 故障排查

#### 问题1：Dashboard无法启动

**症状**：运行start.sh报错

**解决**：
1. 检查Python版本：`python --version` (需要3.8+)
2. 检查依赖：`pip list | grep -i flask`
3. 查看错误日志

#### 问题2：仿真无法启动

**症状**：点击"启动仿真"无响应

**解决**：
1. 检查SUMO_HOME环境变量
2. 检查地图文件是否存在
3. 查看浏览器控制台和服务器日志

#### 问题3：数据不更新

**症状**：地图显示但数据不变化

**解决**：
1. 检查仿真是否真的在运行：`GET /api/simulation/status`
2. 检查JunctionManager是否初始化
3. 检查前端是否正常轮询

#### 问题4：性能问题

**症状**：仿真运行缓慢

**解决**：
1. 使用`nogui=true`模式
2. 减少`step_delay`
3. 增加`scale`（流量倍率）
4. 使用`inference_quick`模式

### 8.5 生产部署建议

#### 使用WSGI服务器

```bash
# 安装gunicorn
pip install gunicorn

# 启动服务
gunicorn -w 4 -b 0.0.0.0:8080 server:app
```

#### 使用Nginx反向代理

```nginx
server {
    listen 80;
    server_name dashboard.example.com;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### 配置日志

```python
# server.py
import logging

logging.basicConfig(
    filename='dashboard.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

#### 性能优化

1. **启用CORS缓存**
2. **使用Redis缓存JunctionAgent数据**
3. **优化前端轮询频率**（根据实际需求调整）
4. **使用WebSocket替代轮询**（实时性要求高时）

---

## 附录

### A. 目录结构完整版

```
dashboard/
├── server.py                    # 主服务器 (1053行)
├── start.sh                     # 启动脚本
├── config.json                  # 主配置文件
├── inference_config.json        # 推理配置
│
├── integration/                 # ===== 集成模块 =====
│   ├── __init__.py
│   ├── junction_agent.py        # 路口智能体 (420行)
│   ├── dashboard_controller.py  # 仿真控制器 (344行)
│   └── dashboard_interface.py   # 接口适配器
│
├── dashboard_tools/             # ===== 工具模块 =====
│   ├── __init__.py
│   ├── README.md                # 工具模块文档
│   ├── training_controller.py   # 训练管理
│   ├── realtime_traffic_data_controller.py  # 实时交通数据
│   ├── models_controller.py     # 模型管理
│   └── continual_learning_controller.py # 持续学习
│
├── simulation_manager.py        # 仿真管理器 (364行)
├── simulation_config.py         # 配置生成器 (340行)
│
├── templates/                   # ===== 前端模板 =====
│   └── index.html              # 主页面
│
└── static/                      # ===== 静态资源 =====
    ├── css/                     # 样式文件
    ├── js/                      # JavaScript
    │   ├── dashboard.js         # 主控制脚本
    │   ├── map_renderer.js      # 地图渲染
    │   └── tools/               # 工具模块前端
    └── html/                    # 其他页面
```

### B. 关键代码统计

| 文件 | 行数 | 功能 |
|------|------|------|
| `server.py` | 1053 | API服务器 |
| `junction_agent.py` | 420 | 路口智能体 |
| `simulation_manager.py` | 364 | 仿真管理 |
| `dashboard_controller.py` | 344 | 仿真控制 |
| `simulation_config.py` | 340 | 配置生成 |
| **总计** | **~2500** | **核心代码** |

### C. 依赖清单

```txt
# 核心依赖
Flask>=2.0.0
Flask-CORS>=3.0.0

# SUMO集成
traci
libsumo

# 数据库（可选）
taos  # TDengine Python客户端

# 工具
numpy
pandas
matplotlib
```

### D. 许可与贡献

本项目为开源项目，欢迎贡献。

---

**文档版本**：v1.0  
**最后更新**：2026-01-08  
**作者**：Dashboard开发团队
