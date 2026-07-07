# Dashboard工具模块

## 概述

工具模块为Dashboard提供了四个核心功能：模型训练、交通数据管理、模型管理和对比实验。每个模块都有独立的控制器和API接口。

## 目录结构

```
dashboard/tools/
├── __init__.py                    # 模块初始化，延迟导入
├── training_controller.py         # 模型训练控制器
├── realtime_traffic_data_controller.py  # 实时交通数据控制器
├── models_controller.py           # 模型管理控制器
├── continual_learning_controller.py  # 持续学习控制器
└── README.md                      # 本文档
```

## 模块说明

### 1. 模型训练 (Training)

**功能**：管理PPO模型的训练流程

**控制器**：`TrainingController`

**主要方法**：
- `start_training(config)` - 启动训练任务
- `stop_training()` - 停止训练任务
- `get_training_status()` - 获取训练状态
- `get_training_logs(limit)` - 获取训练日志

**API端点**：
- `POST /api/tools/training/start` - 启动训练
- `POST /api/tools/training/stop` - 停止训练
- `GET /api/tools/training/status` - 获取状态
- `GET /api/tools/training/logs` - 获取日志

### 2. 交通数据 (Data)

**功能**：管理交通数据的查询、分析和导出

**控制器**：`DataController`

**主要方法**：
- `query_data(query_params)` - 查询交通数据
- `analyze_data(analysis_params)` - 分析交通数据
- `export_data(export_params)` - 导出交通数据
- `get_data_statistics()` - 获取数据统计

**API端点**：
- `POST /api/tools/data/query` - 查询数据
- `POST /api/tools/data/analyze` - 分析数据
- `POST /api/tools/data/export` - 导出数据
- `GET /api/tools/data/statistics` - 获取统计

### 3. 模型管理 (Models)

**功能**：管理PPO模型的存储、加载和版本控制

**控制器**：`ModelsController`

**主要方法**：
- `list_models(filters)` - 列出所有模型
- `load_model(model_id)` - 加载指定模型
- `delete_model(model_id)` - 删除模型
- `get_model_info(model_id)` - 获取模型信息
- `evaluate_model(model_id, eval_params)` - 评估模型

**API端点**：
- `GET /api/tools/models/list` - 列出模型
- `POST /api/tools/models/load` - 加载模型
- `POST /api/tools/models/delete` - 删除模型
- `GET /api/tools/models/info/<model_id>` - 获取模型信息
- `POST /api/tools/models/evaluate` - 评估模型

### 4. 对比实验 (Comparison)

**功能**：管理不同模型和算法的对比实验

**控制器**：`ComparisonController`

**主要方法**：
- `create_experiment(experiment_config)` - 创建实验
- `run_experiment(experiment_id)` - 运行实验
- `stop_experiment(experiment_id)` - 停止实验
- `get_experiment_status(experiment_id)` - 获取实验状态
- `get_experiment_results(experiment_id)` - 获取实验结果
- `list_experiments()` - 列出所有实验
- `generate_report(experiment_id, report_format)` - 生成报告

**API端点**：
- `POST /api/tools/comparison/create` - 创建实验
- `POST /api/tools/comparison/run` - 运行实验
- `POST /api/tools/comparison/stop` - 停止实验
- `GET /api/tools/comparison/status/<experiment_id>` - 获取状态
- `GET /api/tools/comparison/results/<experiment_id>` - 获取结果
- `GET /api/tools/comparison/list` - 列出实验
- `POST /api/tools/comparison/report` - 生成报告

## 前端集成

### 左侧工具栏

工具模块在前端以左侧垂直工具栏的形式呈现，支持：
- 展开/折叠：点击切换按钮
- 折叠状态：仅显示图标
- 展开状态：显示图标+工具名称
- 点击工具项：打开对应的工具界面

### 工具图标

- 🎓 模型训练
- 📊 交通数据
- 🗂️ 模型管理
- 📈 对比实验

### JavaScript API

```javascript
// 切换侧边栏
dashboard.toggleSidebar();

// 打开工具
dashboard.openTool('training');    // 模型训练
dashboard.openTool('data');        // 交通数据
dashboard.openTool('models');      // 模型管理
dashboard.openTool('comparison');  // 对比实验
```

## 开发状态

当前版本为**占位实现**，各模块的核心功能标记为 `TODO`，待后续开发完善。

### 已实现
- ✅ 模块架构和文件结构
- ✅ API路由定义
- ✅ 前端工具栏UI
- ✅ 基础控制器框架

### 待实现
- ⏳ 训练任务的实际执行逻辑
- ⏳ 数据库查询和分析功能
- ⏳ 模型文件管理
- ⏳ 对比实验的运行机制
- ⏳ 前端工具界面的详细设计

## 与其他模块的关系

```
dashboard/
├── integration/          # SUMO集成层
│   ├── junction_agent.py
│   ├── dashboard_controller.py
│   └── dashboard_interface.py
└── tools/                # 工具模块（本模块）
    ├── training_controller.py
    ├── realtime_traffic_data_controller.py
    ├── models_controller.py
    └── continual_learning_controller.py
```

- **integration/**：负责SUMO仿真的实时运行和数据同步
- **tools/**：负责离线任务（训练、数据分析、模型管理、实验对比）

两者相互独立，通过 `server.py` 统一管理。

## 使用示例

### 启动训练任务

```python
# 后端
training_controller.start_training({
    'map_name': '81',
    'epochs': 100,
    'batch_size': 32,
    'learning_rate': 0.0001
})

# 前端
fetch('/api/tools/training/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        map_name: '81',
        epochs: 100,
        batch_size: 32,
        learning_rate: 0.0001
    })
})
```

### 查询交通数据

```python
# 后端
data_controller.query_data({
    'start_time': '2024-01-01 00:00:00',
    'end_time': '2024-01-01 01:00:00',
    'map_name': '81',
    'data_type': 'vehicle'
})

# 前端
fetch('/api/tools/data/query', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        start_time: '2024-01-01 00:00:00',
        end_time: '2024-01-01 01:00:00',
        map_name: '81',
        data_type: 'vehicle'
    })
})
```

## 扩展指南

要实现具体功能，请按以下步骤：

1. **定位控制器**：找到对应的 `*_controller.py` 文件
2. **实现方法**：在标记为 `TODO` 的方法中添加逻辑
3. **测试API**：使用Postman或curl测试API端点
4. **更新前端**：在 `dashboard.js` 中实现对应的UI交互
5. **更新文档**：在本文档中记录新功能

## 注意事项

1. **线程安全**：训练和实验可能在后台线程运行，注意线程同步
2. **资源管理**：确保长时间运行的任务可以正常停止和清理
3. **错误处理**：所有API都应返回统一的JSON格式，包含 `success` 和 `message` 字段
4. **日志记录**：使用 `logging` 模块记录关键操作和错误
5. **配置管理**：考虑将工具模块的配置参数也放入 `config.json`
