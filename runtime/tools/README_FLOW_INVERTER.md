# 交通流量反演系统 Traffic Flow Inverter

从真实检测器数据反演生成SUMO可用的交通路由文件

## 📋 目录

- [功能特性](#功能特性)
- [系统架构](#系统架构)
- [安装依赖](#安装依赖)
- [快速开始](#快速开始)
- [详细使用](#详细使用)
- [数据格式](#数据格式)
- [OD选择策略](#od选择策略)
- [可视化结果](#可视化结果)
- [高级用法](#高级用法)

## 🎯 功能特性

### 核心功能

✅ **数据预处理**
- 支持Excel/CSV格式的流量数据
- 数据清洗和异常值处理
- 时间序列聚合

✅ **网络拓扑构建**
- 解析SUMO路网文件
- 构建有向图数据结构
- 计算节点重要性

✅ **智能OD选择**
- 4种选择策略（boundary/important/balanced/clustered）
- 自动控制计算量
- 支持内部节点选择

✅ **路由计算**
- K最短路径算法
- 基于最大流的流量分配
- 迭代优化算法

✅ **可视化分析**
- 网络拓扑图
- OD矩阵热力图
- 流量对比图
- HTML交互式报告

### 改进点

相比原始flowrouter.py的改进：

1. **更灵活的OD选择** - 不局限于边界节点，支持选择重要内部节点
2. **数据预处理** - 直接处理Excel表格数据
3. **模块化设计** - 清晰的功能分离，易于扩展
4. **丰富的可视化** - 多种图表和交互式报告
5. **计算量控制** - 通过OD对数量限制控制计算复杂度

## 🏗️ 系统架构

```
交通流量反演系统
│
├── 数据预处理模块 (FlowDataProcessor)
│   ├── 加载Excel/CSV数据
│   ├── 数据清洗
│   └── 时间聚合
│
├── 网络构建模块 (NetworkBuilder)
│   ├── 解析SUMO路网
│   ├── 构建拓扑图
│   └── 邻接矩阵
│
├── OD选择模块 (ODSelector)
│   ├── 计算节点重要性
│   ├── 选择策略
│   │   ├── boundary: 边界节点
│   │   ├── important: 重要节点
│   │   ├── balanced: 混合策略
│   │   └── clustered: 聚类选择
│   └── 生成OD对
│
├── 路由计算模块 (RouteCalculator)
│   ├── Dijkstra最短路径
│   ├── K最短路径算法
│   ├── 流量分配
│   └── 迭代优化
│
├── 可视化模块 (Visualizer)
│   ├── 网络拓扑图
│   ├── OD矩阵热力图
│   ├── 流量对比图
│   └── HTML报告
│
└── 输出模块 (RouteExporter)
    ├── SUMO路由文件
    └── OD矩阵CSV
```

## 📦 安装依赖

```bash
# 基础依赖
pip install numpy pandas openpyxl

# 可视化依赖
pip install matplotlib seaborn networkx

# SUMO
# 确保已安装SUMO并设置SUMO_HOME环境变量
export SUMO_HOME=/usr/share/sumo
```

## 🚀 快速开始

### 方法1: 命令行使用

```bash
cd /home/sjx/jx/project/LibSignal/tools

# 基本使用
python traffic_flow_inverter.py \
    --network ../data/raw_data/81/81.net.xml \
    --flow flow_data.xlsx \
    --output output/

# 指定OD策略
python traffic_flow_inverter.py \
    --network ../data/raw_data/81/81.net.xml \
    --flow flow_data.xlsx \
    --od-strategy balanced \
    --max-od-pairs 50 \
    --output output/
```

### 方法2: 使用配置文件

```bash
# 创建配置文件
cp config_example.json my_config.json

# 编辑配置
vim my_config.json

# 运行
python traffic_flow_inverter.py --config my_config.json
```

### 方法3: Python脚本调用

```python
from traffic_flow_inverter import TrafficFlowInverter

config = {
    'network_file': '../data/raw_data/81/81.net.xml',
    'flow_excel': 'flow_data.xlsx',
    'output_dir': 'output/',
    'od_strategy': 'balanced',
    'max_od_pairs': 100
}

inverter = TrafficFlowInverter(config)
inverter.run_pipeline()
```

## 📊 数据格式

### 输入数据格式

#### 1. 流量数据 (Excel/CSV)

期望的表格格式：

| detector_id | edge_id | lane_id  | timestamp | flow | speed | occupancy |
|-------------|---------|----------|-----------|------|-------|-----------|
| det_001     | edge_1  | edge_1_0 | 08:00:00  | 500  | 45.2  | 0.35      |
| det_002     | edge_2  | edge_2_0 | 08:00:00  | 600  | 50.1  | 0.40      |
| det_003     | edge_3  | edge_3_0 | 08:00:00  | 450  | 42.3  | 0.32      |

**字段说明：**
- `detector_id`: 检测器ID
- `edge_id`: 对应的SUMO边ID
- `lane_id`: 车道ID（可选）
- `timestamp`: 时间戳
- `flow`: 流量（车辆数/小时）
- `speed`: 平均速度（km/h，可选）
- `occupancy`: 占有率（0-1，可选）

#### 2. 路网文件

标准SUMO格式 `.net.xml`

```bash
# 如果没有，可以从OSM生成
netconvert --osm-files map.osm -o network.net.xml
```

### 输出文件格式

运行后会在输出目录生成：

```
output/
├── routes.rou.xml          # SUMO路由文件
├── od_matrix.csv           # OD矩阵
├── network_topology.png    # 网络拓扑图
├── od_matrix.png          # OD矩阵热力图
├── route_frequency.png    # 流量对比图
└── report.html            # 交互式HTML报告
```

## 🎯 OD选择策略

### 1. boundary (边界策略)

**特点：** 只选择路网边界节点作为OD

**适用场景：**
- 小范围路网分析
- 外围交通为主
- 快速计算

**优点：**
- ✅ 计算量最小
- ✅ 符合传统交通理论

**缺点：**
- ⚠️ 忽略内部交通

```bash
--od-strategy boundary
```

### 2. important (重要性策略)

**特点：** 选择重要性得分最高的K个节点

**评分标准：**
- 节点度数（连接数）
- 检测器覆盖
- 边界位置
- （待实现）中心性

**适用场景：**
- 需要覆盖主要交通枢纽
- 中等规模路网

```bash
--od-strategy important --max-od-pairs 50
```

### 3. balanced (平衡策略) ⭐推荐

**特点：** 边界节点 + 部分重要内部节点

**选择规则：**
1. 所有边界节点
2. 重要性最高的内部节点（约为边界节点数的50%）

**适用场景：**
- 大多数实际应用
- 兼顾边界和内部交通

```bash
--od-strategy balanced --max-od-pairs 100
```

### 4. clustered (聚类策略)

**特点：** 基于地理位置聚类，选择代表节点

**方法：**
- K-means聚类
- 每个簇选择中心点

**适用场景：**
- 超大规模路网
- 需要区域代表性

```bash
--od-strategy clustered --max-od-pairs 30
```

### 策略对比

| 策略 | OD对数 | 计算时间 | 覆盖范围 | 适用规模 |
|------|--------|----------|----------|----------|
| boundary | 少 | 快 | 边界 | 小 |
| important | 中 | 中 | 枢纽 | 中 |
| balanced | 中-多 | 中 | 全面 | 大 |
| clustered | 少-中 | 慢 | 区域 | 超大 |

## 📈 可视化结果

### 1. 网络拓扑图

![Network Topology](network_topology.png)

- **红色节点**: 选中的OD候选节点
- **蓝色节点**: 普通节点
- **箭头**: 有向边

### 2. OD矩阵热力图

![OD Matrix](od_matrix.png)

- **颜色深浅**: 表示流量大小
- **行**: 起点(Origin)
- **列**: 终点(Destination)

### 3. 流量对比图

![Route Frequency](route_frequency.png)

- **蓝色**: 观测流量
- **橙色**: 估计流量
- 对比前20条流量最大的边

### 4. HTML交互式报告

打开 `report.html` 查看：
- 网络统计信息
- 路由详情
- 交互式图表（待实现）

## 🔧 高级用法

### 1. 自定义节点重要性计算

```python
from traffic_flow_inverter import ODSelector, TrafficNetwork

# 加载网络
network = ...

# 自定义重要性计算
def custom_importance(node):
    score = 0
    # 自定义逻辑
    score += len(node.out_edges) * 20
    if node.coord[0] > 500:  # 东部节点
        score += 50
    return score

# 应用
for node in network.nodes.values():
    node.importance = custom_importance(node)

# 选择OD
selector = ODSelector()
od_pairs = selector.select_od_nodes(network, strategy='important')
```

### 2. 批量处理多个时间段

```python
import pandas as pd
from traffic_flow_inverter import TrafficFlowInverter

# 按小时分割数据
df = pd.read_excel('all_day_flow.xlsx')

for hour in range(24):
    # 筛选该小时数据
    hour_df = df[df['hour'] == hour]
    
    # 配置
    config = {
        'network_file': 'network.net.xml',
        'flow_data': hour_df,  # 直接传DataFrame
        'output_dir': f'output/hour_{hour:02d}/',
        'od_strategy': 'balanced'
    }
    
    # 运行
    inverter = TrafficFlowInverter(config)
    inverter.run_pipeline()
```

### 3. 集成到工作流

```python
# pipeline.py
from traffic_flow_inverter import (
    FlowDataProcessor, 
    NetworkBuilder,
    ODSelector,
    RouteCalculator
)

# 步骤1: 预处理
processor = FlowDataProcessor()
df = processor.load_excel_data('flow.xlsx')
flow_dict = processor.aggregate_flow(df)

# 步骤2: 构建网络
builder = NetworkBuilder()
network = builder.load_sumo_network('network.net.xml')

# 步骤3: 选择OD
selector = ODSelector()
selector.select_od_nodes(network, strategy='balanced', max_od_pairs=50)

# 步骤4: 计算路由
calculator = RouteCalculator()
routes = calculator.calculate_flow_distribution(network, flow_dict)

# 步骤5: 自定义后处理
for route in routes:
    if route.flow < 10:  # 过滤小流量路由
        route.flow = 0

# 步骤6: 导出
# ...
```

## 🐛 调试和问题排查

### 常见问题

**Q1: 提示"未找到SUMO_HOME"**

```bash
# 设置环境变量
export SUMO_HOME=/usr/share/sumo
# 或添加到 ~/.bashrc
echo 'export SUMO_HOME=/usr/share/sumo' >> ~/.bashrc
source ~/.bashrc
```

**Q2: 生成的OD对太少**

- 增加 `--max-od-pairs` 参数
- 尝试 `balanced` 或 `important` 策略

**Q3: 计算时间太长**

- 减少 `--max-od-pairs`
- 使用 `boundary` 策略
- 过滤小流量边

**Q4: 流量估计不准确**

- 检查输入数据质量
- 增加检测器覆盖
- 启用优化: `--optimize`

## 📝 开发计划

### 待实现功能 (TODO)

- [ ] 完整实现K最短路径算法（Yen's算法）
- [ ] 实现中心性计算（betweenness centrality）
- [ ] 基于聚类的OD选择
- [ ] 线性规划优化流量分配
- [ ] 使用plotly生成交互式图表
- [ ] 支持多时段动态OD矩阵
- [ ] GPU加速大规模计算
- [ ] 机器学习预测缺失流量

### 性能优化

- [ ] 缓存最短路径结果
- [ ] 并行计算OD对
- [ ] 稀疏矩阵优化
- [ ] 增量式网络更新

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License

---

**作者**: LibSignal Team  
**更新**: 2026-01-31  
**版本**: 1.0.0

