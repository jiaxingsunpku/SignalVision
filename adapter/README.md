# Dashboard 适配层

## 概述

适配层是连接 Dashboard 前端和训练系统（trainer）的桥梁，采用**标准接口**设计，使得 Dashboard 能够与不同的训练系统对接，而无需修改前端代码。

## 架构设计

```
┌─────────────────────────────────────────┐
│         Dashboard 前端                   │
│   (使用标准接口，不依赖具体实现)          │
└──────────────┬──────────────────────────┘
               │ 调用标准接口
┌──────────────▼──────────────────────────┐
│           Adapter 适配层                 │
│  ┌────────────────────────────────────┐ │
│  │ StandardInterface (抽象基类)        │ │
│  ├────────────────────────────────────┤ │
│  │ - StandardSimulation               │ │
│  │ - StandardSolver                   │ │
│  │ - StandardInterface                │ │
│  │ - StandardArgs                     │ │
│  └────────────────────────────────────┘ │
│  ┌────────────────────────────────────┐ │
│  │ LibSignalAdapter (具体实现)        │ │
│  ├────────────────────────────────────┤ │
│  │ - LibSignalSimulation              │ │
│  │ - LibSignalSolver                  │ │
│  │ - LibSignalInterface               │ │
│  └────────────────────────────────────┘ │
│  ┌────────────────────────────────────┐ │
│  │ ConfigConverter (配置转换)         │ │
│  └────────────────────────────────────┘ │
└──────────────┬──────────────────────────┘
               │ 调用具体实现
┌──────────────▼──────────────────────────┐
│        Trainer 训练系统                  │
│      (LibSignal 框架)                    │
└─────────────────────────────────────────┘
```

## 核心模块

### 1. `standard_interface.py` - 标准接口定义

定义了 Dashboard 期望的标准接口（抽象基类）：

- **StandardArgs**: 标准化参数对象
- **StandardSimulation**: 仿真系统接口
- **StandardSolver**: 算法求解器接口
- **StandardInterface**: Dashboard接口

任何训练系统都需要实现这些接口，以便与 Dashboard 集成。

### 2. `libsignal_adapter.py` - LibSignal 适配器

LibSignal 训练系统的具体实现：

- **LibSignalSimulation**: 封装 LibSignal 的 TSCEnv 和 World
- **LibSignalSolver**: 封装 LibSignal 的 Agent 系统
- **LibSignalInterface**: 连接两者的桥梁

### 3. `config_converter.py` - 配置转换工具

负责在不同参数格式之间转换：

- Dashboard 配置 → StandardArgs
- StandardArgs → LibSignal 参数
- 算法名称映射（maxpressure ↔ maxpressure_agent）
- 场景名称映射（81 ↔ sumo81）

## 使用方法

### Dashboard 端使用

```python
from adapter import (
    StandardArgs,
    LibSignalSimulation,
    LibSignalSolver,
    LibSignalInterface,
    ConfigConverter
)

# 方式1：从配置字典创建
config = {
    'config': 'maxpressure',
    'sim_name': '81',
    'simlen': 3600,
    'nogui': True,
    'scale': 2
}
std_args = ConfigConverter.dashboard_config_to_standard(config)

# 方式2：从命令行参数创建
std_args = StandardArgs()
std_args.sim = '81'
std_args.tsc = 'maxpressure'
std_args.simlen = 3600
std_args.nogui = True

# 创建仿真和算法对象
simulation = LibSignalSimulation(args=std_args, nogui=std_args.nogui)
solver = LibSignalSolver(args=std_args)

# 初始化
simulation.gen_sim()

# 创建接口
interface = LibSignalInterface(
    sim=simulation,
    sys=solver,
    junction_manager=junction_manager,
    step_delay=0.0
)

# 启动仿真
simulation.start()

# 执行步骤
for step in range(100):
    interface.signal_update()  # 决策
    simulation.sim_step()      # 执行
    
    # 获取数据
    netdata = interface.get_netdata()
    cache = interface.subscription_cache
```

### 扩展新的训练系统

如果要支持新的训练系统（如 RESCO、CityFlow等），只需：

1. 创建新的适配器文件（如 `resco_adapter.py`）
2. 实现标准接口（StandardSimulation、StandardSolver、StandardInterface）
3. 在 `__init__.py` 中导出新适配器
4. Dashboard 代码无需修改

示例：

```python
# resco_adapter.py
from .standard_interface import StandardSimulation, StandardSolver, StandardInterface

class RESCOSimulation(StandardSimulation):
    def __init__(self, args, nogui=True):
        # 实现 RESCO 仿真初始化
        pass
    
    def gen_sim(self):
        # 实现 RESCO 环境生成
        pass
    
    # ... 实现其他方法

class RESCOSolver(StandardSolver):
    # 实现 RESCO 算法
    pass

class RESCOInterface(StandardInterface):
    # 实现 RESCO 接口
    pass
```

## 配置映射

### 算法名称映射

| Dashboard | LibSignal Agent |
|-----------|-----------------|
| maxpressure | maxpressure_agent |
| ppo | colight_pytorch_agent |
| fixedtime | fixedtime_agent |
| colight | colight_pytorch_agent |

### 场景名称映射

| Dashboard | LibSignal Network |
|-----------|-------------------|
| 81 | sumo81 |
| hangzhou | sumohz4x4 |

## 参数说明

### StandardArgs 主要参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| sim | str | '81' | 场景名称 |
| tsc | str | 'maxpressure' | 算法类型 |
| mode | str | 'test' | 运行模式 |
| nogui | bool | True | 是否无GUI |
| simlen | int | 3600 | 仿真时长（秒） |
| scale | float | 2.0 | 流量倍率 |
| enable_db | bool | False | 是否启用数据库 |
| step_delay | float | 0.0 | 步骤延迟（秒） |

## 目录结构

```
rebuild/adapter/
├── __init__.py                 # 模块初始化，导出公共接口
├── README.md                   # 本文档
├── standard_interface.py       # 标准接口定义（抽象基类）
├── config_converter.py         # 配置转换工具
└── libsignal_adapter.py        # LibSignal 适配器实现
```

## 设计理念

### 1. 依赖倒置原则

Dashboard 依赖于抽象接口（StandardInterface），而不是具体实现（LibSignal）。
这样，当需要更换训练系统时，只需实现新的适配器，Dashboard 代码无需修改。

### 2. 开闭原则

对扩展开放（可以添加新的适配器），对修改关闭（Dashboard 代码稳定）。

### 3. 单一职责原则

- 标准接口：定义契约
- 适配器：实现契约
- 配置转换器：处理参数转换

## 故障排查

### 问题：无法导入 LibSignal 模块

**原因**：trainer 目录不在 Python 路径中。

**解决方案**：
```python
import sys
from pathlib import Path
RUNTIME_ROOT = Path(__file__).parent.parent / 'runtime'
sys.path.insert(0, str(RUNTIME_ROOT))
```

### 问题：参数格式不兼容

**原因**：Dashboard 和 LibSignal 使用不同的参数名称。

**解决方案**：使用 `ConfigConverter` 进行转换：
```python
std_args = ConfigConverter.dashboard_config_to_standard(config)
```

### 问题：路网文件找不到

**原因**：工作目录不正确。

**解决方案**：在初始化前切换到正确的目录：
```python
import os
os.chdir(PROJECT_ROOT / 'runtime')
```

## 未来扩展

### 支持更多训练系统

- [ ] RESCO 框架适配器
- [ ] CityFlow 框架适配器
- [ ] SUMO-RL 框架适配器

### 功能增强

- [ ] 支持多仿真器并行
- [ ] 支持实时算法切换
- [ ] 支持模型热加载
- [ ] 支持分布式训练集成

## 贡献指南

如果要添加新的适配器或改进现有代码：

1. 确保遵循标准接口定义
2. 添加完整的类型注解
3. 编写单元测试
4. 更新本文档

## 许可证

与主项目保持一致
