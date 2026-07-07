# ============================================================
# Traffic Flow Inversion Tools - Usage Commands
# ============================================================

# --------------------- extract_flow_from_routes.py ---------------------
# 从SUMO路由文件提取流量数据，生成测试样例

# 81地图：提取流量并生成每小时热力图
python extract_flow_from_routes.py --network ../data/raw_data/81/81.net.xml --routes ../data/raw_data/81/81.rou.xml --output output/flow_test_data --visualize

# Manhattan地图：提取流量并生成每小时热力图
python extract_flow_from_routes.py --network ../data/raw_data/manhattan_28x7/manhattan_28x7.net.xml --routes ../data/raw_data/manhattan_28x7/manhattan_28x7.rou.xml --output output/flow_manhattan_28x7 --visualize

# 只生成第0小时的热力图
python extract_flow_from_routes.py --network ../data/raw_data/81/81.net.xml --routes ../data/raw_data/81/81.rou.xml --output output/flow_test_data --hour 0

# 只提取数据，不生成热力图
python extract_flow_from_routes.py --network ../data/raw_data/81/81.net.xml --routes ../data/raw_data/81/81.rou.xml --output output/flow_test_data --no-visualize


# --------------------- traffic_flow_inverter.py ---------------------
# 交通流量反演系统，从观测流量生成OD矩阵和路由

# === 单时段处理 ===

# 81地图：使用观测流量数据计算OD矩阵（中位数估计算法）
python traffic_flow_inverter.py --network ../data/raw_data/81/81.net.xml --flow-data output/flow_test_data/flow_hour_0.csv --output-dir output/81_od_median --od-algorithm median

# 81地图：使用最小二乘法算法
python traffic_flow_inverter.py --network ../data/raw_data/81/81.net.xml --flow-data output/flow_test_data/flow_hour_0.csv --output-dir output/81_od_lse --od-algorithm lse

# === 多时段处理 ===

# --- Median算法（中位数估计）---
# Manhattan地图：默认参数（采样50%，距离阈值20%）
python traffic_flow_inverter.py --network ../data/raw_data/manhattan_28x7/manhattan_28x7.net.xml --flow-dir output/flow_manhattan_28x7 --hours 2 --output-dir output/manhattan_28x7_od_median --od-algorithm median

# Manhattan地图：调整参数（采样80%，距离阈值10%）
python traffic_flow_inverter.py --network ../data/raw_data/manhattan_28x7/manhattan_28x7.net.xml --flow-dir output/flow_manhattan_28x7 --hours 2 --output-dir output/manhattan_28x7_od_median_80_10 --od-algorithm median --od-sampling-ratio 0.8 --min-od-distance-ratio 0.1

# --- LSE算法（非负最小二乘法）---
# Manhattan地图：默认参数（采样50%，距离阈值20%）
python traffic_flow_inverter.py --network ../data/raw_data/manhattan_28x7/manhattan_28x7.net.xml --flow-dir output/flow_manhattan_28x7 --hours 2 --output-dir output/manhattan_28x7_od_lse --od-algorithm lse

# Manhattan地图：调整参数（采样80%，距离阈值10%）
python traffic_flow_inverter.py --network ../data/raw_data/manhattan_28x7/manhattan_28x7.net.xml --flow-dir output/flow_manhattan_28x7 --hours 2 --output-dir output/manhattan_28x7_od_lse_80_10 --od-algorithm lse --od-sampling-ratio 0.8 --min-od-distance-ratio 0.1

# === 测试和调试 ===

# 仅可视化网络拓扑（不计算OD）
python traffic_flow_inverter.py --network ../data/raw_data/81/81.net.xml --output-dir output/81_topology --visualize-only

# 测试OD节点选择（不导出结果）
python traffic_flow_inverter.py --network ../data/raw_data/81/81.net.xml --output-dir output/81_od_test --visualize-only

# 计算OD矩阵但不导出路由文件（仅测试和可视化）
python traffic_flow_inverter.py --network ../data/raw_data/81/81.net.xml --flow-data output/flow_test_data/flow_hour_0.csv --output-dir output/81_od_test --skip-export

# 使用统一初始流量（不使用观测数据）
python traffic_flow_inverter.py --network ../data/raw_data/81/81.net.xml --output-dir output/81_uniform --initial-flow 100.0


# --------------------- 参数说明 ---------------------

# extract_flow_from_routes.py:
#   -n, --network    : SUMO网络文件 (.net.xml)
#   -r, --routes     : SUMO路由文件 (.rou.xml)
#   -o, --output     : 输出目录
#   --hour N         : 可视化第N小时的流量（不指定则为所有小时）
#   --visualize      : 生成热力图（默认开启）
#   --no-visualize   : 不生成热力图

# traffic_flow_inverter.py:
#   -n, --network       : SUMO网络文件 (.net.xml)
#   --flow-data FILE    : 单个流量数据文件 (.csv, 格式: edge_id,flow)
#   --flow-dir DIR      : 流量数据目录（包含flow_hour_*.csv）
#   --hours N           : 总时段数（小时），配合--flow-dir使用，默认1
#   -o, --output-dir    : 输出目录
#   --od-strategy       : OD选择策略 (仅支持 traffic_light_density)
#                         默认: traffic_light_density（基于信号灯节点和密度）
#   --od-sampling-ratio : 内部信号灯节点采样比例 (0.0-1.0)，默认: 0.5（50%）
#   --min-od-distance-ratio : 最小OD距离比例（相对于地图尺度），默认: 0.2（20%）
#   --od-algorithm      : OD流量计算算法 (median=中位数估计, lse=最小二乘法)
#                         默认: median
#   --initial-flow      : 初始流量值（无观测数据时使用），默认100.0
#   --visualize-only    : 仅可视化网络拓扑
#   --skip-export       : 跳过结果导出

