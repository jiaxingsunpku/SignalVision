#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整的交通流量反演系统
从真实检测器数据反演生成SUMO路由文件

主要功能：
1. 预处理流量数据（Excel/CSV）
2. 构建路网拓扑图
3. 智能选择OD节点
4. 基于最大流算法计算路由
5. 可视化分析结果

"""

import os
import sys
import json
import pickle
import argparse
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Set, Optional
import xml.etree.ElementTree as ET
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import Normalize

# 过滤matplotlib弃用警告
warnings.filterwarnings('ignore', category=DeprecationWarning, module='matplotlib')

# 添加SUMO工具路径
if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
    import sumolib
else:
    print("警告: 未设置SUMO_HOME环境变量")


# ==================== 1. 数据结构定义 ====================

class Node:
    """路网节点"""
    def __init__(self, node_id: str, coord: Tuple[float, float] = None):
        self.id = node_id
        self.coord = coord  # (x, y)
        self.in_edges = []   # 入边列表
        self.out_edges = []  # 出边列表
        self.is_od_candidate = False  # 是否为OD候选点
        self.importance = 0.0  # 节点重要性得分
        self.has_traffic_light = False  # 是否有信号灯
        self.density = 0.0  # 节点密度（周围流量/连接密度）
        
    def __repr__(self):
        return f"Node({self.id})"


class Edge:
    """路网边"""
    def __init__(self, edge_id: str, from_node: Node, to_node: Node):
        self.id = edge_id
        self.from_node = from_node
        self.to_node = to_node
        self.length = 0.0
        self.num_lanes = 1
        self.max_speed = 13.89  # 默认50km/h
        self.capacity = 0  # 通行能力
        self.observed_flow = None  # 观测流量
        self.estimated_flow = 0.0  # 估计流量
        self.routes = []  # 经过该边的路由
        
    def get_travel_time(self):
        """计算通行时间"""
        return self.length / self.max_speed if self.max_speed > 0 else float('inf')
    
    def __repr__(self):
        return f"Edge({self.id})"


class Route:
    """路由"""
    def __init__(self, route_id: str, edges: List[Edge], flow: float = 0.0):
        self.id = route_id
        self.edges = edges
        self.flow = flow  # 流量（车辆数/小时）
        self.origin = edges[0].from_node if edges else None
        self.destination = edges[-1].to_node if edges else None
        
    def get_edge_ids(self):
        """获取边ID列表"""
        return [e.id for e in self.edges]
    
    def get_total_length(self):
        """获取路由总长度"""
        return sum(e.length for e in self.edges)
    
    def __repr__(self):
        return f"Route({self.id}, flow={self.flow:.1f})"


class TrafficNetwork:
    """交通网络拓扑"""
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Edge] = {}
        self.od_pairs: List[Tuple[Node, Node]] = []
        self.routes: List[Route] = []
        
    def add_node(self, node: Node):
        """添加节点"""
        self.nodes[node.id] = node
        
    def add_edge(self, edge: Edge):
        """添加边"""
        self.edges[edge.id] = edge
        edge.from_node.out_edges.append(edge)
        edge.to_node.in_edges.append(edge)
    
    def get_statistics(self):
        """获取网络统计信息"""
        return {
            'num_nodes': len(self.nodes),
            'num_edges': len(self.edges),
            'num_od_pairs': len(self.od_pairs),
            'num_routes': len(self.routes),
            'total_flow': sum(r.flow for r in self.routes)
        }


# ==================== 2. 数据预处理模块 ====================

class FlowDataProcessor:
    """流量数据预处理器"""
    
    @staticmethod
    def load_csv_data(filepath: str) -> pd.DataFrame:
        """
        从CSV加载流量数据
        
        期望格式：
        | edge_id | flow |
        |---------|------|
        | -E0     | 17   |
        | -E1     | 33   |
        """
        print(f"正在加载流量数据: {filepath}")
        
        if filepath and os.path.exists(filepath):
            df = pd.read_csv(filepath)
            print(f"  - 加载 {len(df)} 条流量记录")
            return df
        else:
            print(f"  - 文件不存在，使用示例数据")
            # 占位：生成示例数据
            df = pd.DataFrame({
                'edge_id': ['edge_1', 'edge_2', 'edge_3'],
                'flow': [500, 600, 450]
            })
            print(f"  - 加载 {len(df)} 条流量记录")
            return df
    
    @staticmethod
    def aggregate_flow(df: pd.DataFrame, time_interval: int = 3600) -> Dict[str, float]:
        """
        聚合流量数据到边级别
        
        参数:
            df: 流量数据 (CSV格式: edge_id, flow)
            time_interval: 时间区间（秒）
        
        返回:
            Dict[edge_id, total_flow]
        """
        print(f"正在处理流量数据")
        
        # CSV格式已经是聚合后的数据：edge_id, flow
        if 'edge_id' in df.columns and 'flow' in df.columns:
            flow_dict = dict(zip(df['edge_id'], df['flow']))
        else:
            # 兼容旧格式
            flow_dict = df.groupby('edge_id')['flow'].sum().to_dict()
        
        print(f"  - 处理 {len(flow_dict)} 条边的流量")
        return flow_dict
    
    @staticmethod
    def clean_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        清洗数据：去除异常值、填充缺失值等
        """
        print("正在清洗数据")
        
        # TODO: 实际实现数据清洗
        # 1. 去除异常值（如负流量、超大流量）
        df = df[df['flow'] >= 0]
        df = df[df['flow'] < 10000]  # 假设单车道每小时不超过10000辆
        
        # 2. 填充缺失值
        df = df.fillna(0)
        
        print(f"  - 清洗后保留 {len(df)} 条记录")
        return df
    
    @staticmethod
    def export_sumo_detector_format(flow_dict: Dict[str, float], 
                                   output_path: str):
        """导出为SUMO检测器格式"""
        print(f"正在导出检测器数据: {output_path}")
        
        # TODO: 生成SUMO检测器XML格式
        root = ET.Element('detectors')
        
        for edge_id, flow in flow_dict.items():
            det = ET.SubElement(root, 'e1Detector')
            det.set('id', f'det_{edge_id}')
            det.set('lane', f'{edge_id}_0')
            det.set('pos', '50')
            det.set('freq', '3600')
            det.set('file', 'NUL')
        
        tree = ET.ElementTree(root)
        ET.indent(tree, space='    ')
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        
        print(f"  - 导出 {len(flow_dict)} 个检测器")


# ==================== 3. 路网拓扑构建模块 ====================

class NetworkBuilder:
    """路网拓扑构建器"""
    
    @staticmethod
    def load_sumo_network(net_file: str) -> TrafficNetwork:
        """
        从SUMO路网文件加载拓扑
        
        参数:
            net_file: SUMO .net.xml文件路径
        
        返回:
            TrafficNetwork对象
        """
        print(f"正在加载SUMO路网: {net_file}")
        
        network = TrafficNetwork()
        
        # 检查文件是否存在
        if not os.path.exists(net_file):
            print(f"  ✗ 错误: 文件不存在: {net_file}")
            return network
        
        try:
            # 使用sumolib解析路网
            if 'sumolib' not in sys.modules:
                raise ImportError("sumolib未导入")
            
            net = sumolib.net.readNet(net_file)
            
            # 1. 先获取所有信号灯节点的ID
            tls_node_ids = set()
            for tls in net.getTrafficLights():
                # 信号灯的ID通常就是它所在节点的ID
                tls_node_ids.add(tls.getID())
            
            # 2. 加载节点
            for sumo_node in net.getNodes():
                node_id = sumo_node.getID()
                coord = sumo_node.getCoord()
                node = Node(node_id, coord=coord)
                
                # 标记信号灯节点
                if node_id in tls_node_ids:
                    node.has_traffic_light = True
                
                network.add_node(node)
            
            # 2. 加载边（排除内部边）
            for sumo_edge in net.getEdges():
                # 跳过内部边（交叉口内部连接）
                if sumo_edge.isSpecial() or sumo_edge.getFunction() == 'internal':
                    continue
                
                edge_id = sumo_edge.getID()
                from_node_id = sumo_edge.getFromNode().getID()
                to_node_id = sumo_edge.getToNode().getID()
                
                # 创建边对象
                if from_node_id in network.nodes and to_node_id in network.nodes:
                    edge = Edge(edge_id, 
                               network.nodes[from_node_id],
                               network.nodes[to_node_id])
                    
                    # 设置边属性
                    edge.length = sumo_edge.getLength()
                    edge.num_lanes = sumo_edge.getLaneNumber()
                    edge.max_speed = sumo_edge.getSpeed()
                    
                    network.add_edge(edge)
            
            # 统计信号灯节点
            tls_count = sum(1 for n in network.nodes.values() if n.has_traffic_light)
            
            stats = network.get_statistics()
            print(f"  ✓ 成功加载")
            print(f"    - 节点数: {stats['num_nodes']}")
            print(f"    - 信号灯节点: {tls_count}")
            print(f"    - 边数: {stats['num_edges']}")
            
        except ImportError as e:
            print(f"  ✗ 警告: 无法使用sumolib ({e})，使用示例网络")
            # 创建示例网络作为后备
            for i in range(10):
                node = Node(f'node_{i}', coord=(i*100, i*50))
                network.add_node(node)
            
            for i in range(9):
                edge = Edge(f'edge_{i}', 
                           network.nodes[f'node_{i}'],
                           network.nodes[f'node_{i+1}'])
                edge.length = 100.0
                edge.num_lanes = 2
                edge.max_speed = 13.89
                network.add_edge(edge)
            
            stats = network.get_statistics()
            print(f"  - 使用示例网络: {stats['num_nodes']} 节点, {stats['num_edges']} 边")
        
        except Exception as e:
            print(f"  ✗ 错误: 加载失败 - {e}")
            import traceback
            traceback.print_exc()
        
        return network
    
    @staticmethod
    def build_adjacency_matrix(network: TrafficNetwork) -> np.ndarray:
        """
        构建邻接矩阵
        
        返回:
            adj_matrix: [N, N] 邻接矩阵
        """
        print("正在构建邻接矩阵")
        
        node_list = list(network.nodes.keys())
        n = len(node_list)
        node_idx = {nid: i for i, nid in enumerate(node_list)}
        
        adj_matrix = np.zeros((n, n))
        
        for edge in network.edges.values():
            i = node_idx[edge.from_node.id]
            j = node_idx[edge.to_node.id]
            adj_matrix[i, j] = 1
        
        print(f"  - 邻接矩阵大小: {adj_matrix.shape}")
        print(f"  - 连接数: {int(adj_matrix.sum())}")
        
        return adj_matrix
    
    @staticmethod
    def save_network(network: TrafficNetwork, filepath: str):
        """保存网络到文件"""
        print(f"正在保存网络: {filepath}")
        
        with open(filepath, 'wb') as f:
            pickle.dump(network, f)
        
        print(f"  - 保存成功")
    
    @staticmethod
    def load_network(filepath: str) -> TrafficNetwork:
        """从文件加载网络"""
        print(f"正在加载网络: {filepath}")
        
        with open(filepath, 'rb') as f:
            network = pickle.load(f)
        
        stats = network.get_statistics()
        print(f"  - 加载成功: {stats}")
        
        return network


# ==================== 4. OD节点选择模块 ====================

class ODSelector:
    """OD节点智能选择器"""
    
    @staticmethod
    def calculate_node_density(network: TrafficNetwork) -> Dict[str, float]:
        """
        计算节点密度
        
        密度定义：节点的连接度 × 周围边的容量总和
        密度越高，表示该节点周围交通越繁忙，越可能是重要的OD点
        """
        print("正在计算节点密度")
        
        density = {}
        
        for node_id, node in network.nodes.items():
            # 基础密度：连接度（入度+出度）
            degree = len(node.in_edges) + len(node.out_edges)
            
            # 容量密度：周围边的总容量/流量
            total_capacity = 0.0
            for edge in node.in_edges + node.out_edges:
                # 使用车道数作为容量指标
                total_capacity += edge.num_lanes
            
            # 综合密度得分
            node_density = degree * (1 + total_capacity)
            
            density[node_id] = node_density
            node.density = node_density
        
        if density:
            min_d = min(density.values())
            max_d = max(density.values())
            print(f"  - 密度范围: [{min_d:.1f}, {max_d:.1f}]")
        
        return density
    
    @staticmethod
    def calculate_node_importance(network: TrafficNetwork) -> Dict[str, float]:
        """
        计算节点重要性
        
        评分标准：
        1. 连接度（入度+出度）
        2. 中心性（betweenness centrality）
        3. 检测器覆盖
        4. 地理位置（边界优先）
        """
        print("正在计算节点重要性")
        
        importance = {}
        
        for node_id, node in network.nodes.items():
            score = 0.0
            
            # 1. 连接度得分
            degree = len(node.in_edges) + len(node.out_edges)
            score += degree * 10
            
            # 2. 边界节点得分（入度=0或出度=0）
            if len(node.in_edges) == 0 or len(node.out_edges) == 0:
                score += 50
            
            # 3. TODO: 中心性得分（需要图算法）
            # betweenness = calculate_betweenness(node)
            # score += betweenness * 20
            
            # 4. 检测器覆盖得分
            has_detector = any(e.observed_flow is not None 
                             for e in node.out_edges + node.in_edges)
            if has_detector:
                score += 30
            
            importance[node_id] = score
            node.importance = score
        
        if importance:
            print(f"  - 计算完成，得分范围: [{min(importance.values()):.1f}, {max(importance.values()):.1f}]")
        else:
            print(f"  - 警告: 无节点数据")
        
        return importance
    
    @staticmethod
    def select_od_nodes(network: TrafficNetwork, 
                       max_od_pairs: int = 100,
                       strategy: str = 'traffic_light_density',
                       sampling_ratio: float = 0.5,
                       min_distance_ratio: float = 0.2) -> List[Tuple[Node, Node]]:
        """
        智能选择OD节点对（基于信号灯节点和密度）
        
        参数:
            network: 交通网络
            max_od_pairs: 最大OD对数量（控制计算量，已废弃）
            strategy: 选择策略（仅支持 'traffic_light_density'）
            sampling_ratio: 内部信号灯节点的采样比例（0.0-1.0），默认0.5
            min_distance_ratio: 最小OD距离比例（相对于地图尺度），默认0.2
        
        返回:
            [(origin_node, destination_node), ...]
        
        策略说明:
            1. 筛选所有信号灯节点
            2. 计算节点密度（连接度 × 车道容量）
            3. 边界节点：入度<=1 或 出度<=1
            4. 内部节点：从信号灯节点中按密度加权随机选择（比例由sampling_ratio控制）
            5. OD候选 = 所有边界节点 + 选择的内部节点
            6. 过滤过近的OD对（直线距离 < 地图尺度 × min_distance_ratio）
        """
        print(f"正在选择OD节点（策略: {strategy}, 采样比例: {sampling_ratio*100:.0f}%, 距离阈值: {min_distance_ratio*100:.0f}%）")
        
        od_pairs = []
        
        # 基于信号灯节点和密度的选择
        # 1. 筛选信号灯节点
        tls_nodes = [n for n in network.nodes.values() if n.has_traffic_light]
        
        if len(tls_nodes) == 0:
            print("  ⚠️  警告: 未找到信号灯节点，使用所有节点")
            tls_nodes = list(network.nodes.values())
        
        print(f"    - 发现 {len(tls_nodes)} 个信号灯节点")
        
        # 2. 计算节点密度
        ODSelector.calculate_node_density(network)
        
        # 3. 分离边界节点和内部节点
        # 边界节点：入度<=1 或 出度<=1（适用于网络出入口）
        boundary_nodes = [n for n in network.nodes.values() 
                         if len(n.in_edges) <= 1 or len(n.out_edges) <= 1]
        
        # 内部节点：仅从信号灯节点中选择
        internal_tls = [n for n in tls_nodes 
                       if len(n.in_edges) > 0 and len(n.out_edges) > 0]
        
        print(f"    - 边界节点: {len(boundary_nodes)}")
        print(f"    - 内部信号灯节点: {len(internal_tls)}")
        
        # 4. 选择内部节点：按密度加权随机选择
        if len(internal_tls) > 0:
            # 计算选择数量
            num_internal_select = max(1, int(len(internal_tls) * sampling_ratio))
            
            # 按密度加权
            densities = np.array([n.density for n in internal_tls])
            # 归一化为概率
            if densities.sum() > 0:
                probabilities = densities / densities.sum()
            else:
                probabilities = np.ones(len(internal_tls)) / len(internal_tls)
            
            # 加权随机选择（不重复）
            selected_indices = np.random.choice(
                len(internal_tls),
                size=min(num_internal_select, len(internal_tls)),
                replace=False,
                p=probabilities
            )
            
            selected_internal = [internal_tls[i] for i in selected_indices]
            
            print(f"    - 选择内部节点: {len(selected_internal)} (密度加权随机)")
            print(f"      平均密度: {np.mean([n.density for n in selected_internal]):.1f}")
        else:
            selected_internal = []
        
        # 5. 组合：全部边界节点 + 选择的内部节点
        origins = destinations = boundary_nodes + selected_internal
        
        print(f"    - 总OD候选节点: {len(origins)}")
        
        # 计算地图尺度（用于距离过滤）
        all_coords = [n.coord for n in network.nodes.values() if n.coord]
        if all_coords:
            xs = [c[0] for c in all_coords]
            ys = [c[1] for c in all_coords]
            map_scale = max(max(xs) - min(xs), max(ys) - min(ys))
            distance_threshold = map_scale * min_distance_ratio
            print(f"    - 地图尺度: {map_scale:.1f}m, 最小OD距离阈值: {distance_threshold:.1f}m ({min_distance_ratio*100:.0f}%)")
        else:
            distance_threshold = 0
        
        # 生成OD对（避免自环和过近的OD）
        filtered_count = 0
        for o in origins:
            for d in destinations:
                if o.id != d.id:
                    # 检查直线距离
                    if o.coord and d.coord:
                        dist = np.sqrt((o.coord[0] - d.coord[0])**2 + 
                                      (o.coord[1] - d.coord[1])**2)
                        if dist < distance_threshold:
                            filtered_count += 1
                            continue
                    
                    od_pairs.append((o, d))
                    o.is_od_candidate = True
                    d.is_od_candidate = True
        
        network.od_pairs = od_pairs
        
        print(f"  - 选择了 {len(set(origins))} 个起点")
        print(f"  - 选择了 {len(set(destinations))} 个终点")
        print(f"  - 过滤过近OD对: {filtered_count} 个")
        print(f"  - 生成 {len(od_pairs)} 个OD对（不限制数量）")
        
        return od_pairs


# ==================== 5. 路由计算模块 ====================

class RouteCalculator:
    """路由计算器（基于最大流算法）"""
    
    @staticmethod
    def dijkstra_shortest_path(network: TrafficNetwork, 
                              origin: Node, 
                              destination: Node) -> List[Edge]:
        """
        使用Dijkstra算法计算最短路径（基于实际道路长度）
        
        返回:
            edges: 路径上的边序列
        """
        import heapq
        
        # 初始化距离和前驱
        distances = {node.id: float('inf') for node in network.nodes.values()}
        distances[origin.id] = 0
        previous_edge = {}  # 记录到达每个节点的边
        
        # 优先队列：(距离, 节点ID)
        pq = [(0, origin.id)]
        visited = set()
        
        while pq:
            current_dist, current_id = heapq.heappop(pq)
            
            if current_id in visited:
                continue
            visited.add(current_id)
            
            # 找到目标节点，重建路径
            if current_id == destination.id:
                path = []
                node_id = destination.id
                while node_id in previous_edge:
                    edge = previous_edge[node_id]
                    path.append(edge)
                    node_id = edge.from_node.id
                return list(reversed(path))
            
            # 松弛操作
            current_node = network.nodes[current_id]
            for edge in current_node.out_edges:
                next_node = edge.to_node
                if next_node.id in visited:
                    continue
                
                # 使用边的实际长度作为权重
                new_dist = current_dist + edge.length
                
                if new_dist < distances[next_node.id]:
                    distances[next_node.id] = new_dist
                    previous_edge[next_node.id] = edge
                    heapq.heappush(pq, (new_dist, next_node.id))
        
        return []  # 未找到路径
    
    @staticmethod
    def k_shortest_paths(network: TrafficNetwork,
                        origin: Node,
                        destination: Node,
                        k: int = 3) -> List[List[Edge]]:
        """
        计算K条最短路径
        
        使用Yen's算法或类似方法
        """
        # TODO: 实现Yen's K最短路径算法
        
        # 当前：只返回1条最短路径
        shortest = RouteCalculator.dijkstra_shortest_path(network, origin, destination)
        if shortest:
            return [shortest]
        return []
    
    @staticmethod
    def calculate_routes_simple(network: TrafficNetwork, 
                               initial_flow: float = 100.0) -> List[Route]:
        """
        简化版路径计算：为每个OD对计算最短路径，初始化为统一流量值
        
        参数:
            network: 交通网络
            initial_flow: 初始流量值（OD矩阵的非零分量统一值）
        
        返回:
            routes: 路由列表
        """
        print(f"正在计算路径（初始流量: {initial_flow}）")
        
        routes = []
        total_od = len(network.od_pairs)
        success_count = 0
        fail_count = 0
        
        for idx, (origin, dest) in enumerate(network.od_pairs, 1):
            if idx % 50 == 0 or idx == total_od:
                print(f"  - 进度: {idx}/{total_od}")
            
            # 计算最短路径
            path_edges = RouteCalculator.dijkstra_shortest_path(network, origin, dest)
            
            if path_edges:
                route = Route(
                    route_id=f"route_{idx}",
                    edges=path_edges,
                    flow=initial_flow  # 统一初始化
                )
                routes.append(route)
                success_count += 1
            else:
                fail_count += 1
        
        network.routes = routes
        
        print(f"  ✓ 路径计算完成")
        print(f"    - 成功: {success_count} 条")
        print(f"    - 失败: {fail_count} 条")
        print(f"    - 平均路径长度: {np.mean([len(r.edges) for r in routes]):.1f} 条边")
        
        return routes
    
    @staticmethod
    def calculate_flow_distribution(network: TrafficNetwork,
                                   observed_flows: Dict[str, float]) -> List[Route]:
        """
        基于最大流算法计算OD流量分配（仿照flowrouter.py）
        
        核心思想：
        1. 创建超级源点和超级汇点
        2. 将OD起点连接到超级源，OD终点连接到超级汇
        3. 为有观测流量的边设置容量约束
        4. 使用迭代增广路径方法分配流量
        5. 每次找到一条路径，分配流量并记录路由
        
        参数:
            network: 交通网络
            observed_flows: 观测流量 {edge_id: flow}
        
        返回:
            routes: 路由列表及其流量
        """
        print("正在使用最大流算法计算OD矩阵")
        print(f"  - 观测边数: {len(observed_flows)}")
        
        # 1. 初始化：记录观测流量
        total_observed_flow = 0
        for edge_id, flow in observed_flows.items():
            if edge_id in network.edges:
                network.edges[edge_id].observed_flow = flow
                total_observed_flow += flow
        
        print(f"  - 总观测流量: {total_observed_flow:.0f} 辆/小时")
        print(f"  - OD对数量: {len(network.od_pairs)}")
        
        # 2. 为每个OD对计算路径
        print(f"  - 计算所有OD对的路径")
        od_paths = {}
        for idx, (origin, dest) in enumerate(network.od_pairs, 1):
            if idx % 500 == 0:
                print(f"    路径计算进度: {idx}/{len(network.od_pairs)}")
            
            path_edges = RouteCalculator.dijkstra_shortest_path(network, origin, dest)
            if path_edges:
                od_paths[(origin.id, dest.id)] = path_edges
        
        print(f"  - 成功计算 {len(od_paths)} 条路径")
        
        # 3. 统计每条边被多少OD路径使用
        edge_usage_count = defaultdict(int)
        for path_edges in od_paths.values():
            for edge in path_edges:
                edge_usage_count[edge.id] += 1
        
        # 4. 为每个OD对估算流量
        # 核心思想：观测流量 = 所有经过该边的OD对流量之和
        # 因此每个OD对分配到的流量 ≈ 观测流量 / 使用该边的OD对数量
        print(f"  - 估算OD流量")
        od_flows = {}
        
        for (o_id, d_id), path_edges in od_paths.items():
            # 找出路径上有观测流量的边
            observed_edges_on_path = [e for e in path_edges if e.observed_flow is not None]
            
            if observed_edges_on_path:
                # 对每条观测边，估算该OD对在此边的流量贡献
                flow_estimates = []
                for edge in observed_edges_on_path:
                    # 该边的观测流量 / 使用该边的OD对数量
                    usage_count = edge_usage_count.get(edge.id, 1)
                    estimated_contribution = edge.observed_flow / usage_count
                    flow_estimates.append(estimated_contribution)
                
                # 使用中位数作为该OD对的流量（避免异常值影响）
                od_flow = np.median(flow_estimates)
            else:
                # 路径上没有观测边，使用全局平均值
                od_flow = total_observed_flow / len(od_paths)
            
            od_flows[(o_id, d_id)] = od_flow
        
        # 5. 创建路由
        routes = []
        route_id = 0
        
        for (o_id, d_id), path_edges in od_paths.items():
            flow = od_flows.get((o_id, d_id), 0)
            
            if flow > 0:
                route = Route(f'route_{route_id}', path_edges, flow)
                routes.append(route)
                route_id += 1
                
                # 更新边的估计流量
                for edge in path_edges:
                    edge.estimated_flow += flow
                    edge.routes.append(route)
        
        network.routes = routes
        
        # 6. 输出统计信息
        total_allocated_flow = sum(r.flow for r in routes)
        print(f"  ✓ OD矩阵计算完成")
        print(f"    - 成功路由: {len(routes)}/{len(network.od_pairs)}")
        print(f"    - 总分配流量: {total_allocated_flow:.0f} 辆/小时")
        print(f"    - 平均OD流量: {total_allocated_flow/len(routes):.1f} 辆/小时" if routes else "")
        
        # 7. 计算拟合度
        if observed_flows:
            errors = []
            for edge_id, obs_flow in observed_flows.items():
                if edge_id in network.edges:
                    est_flow = network.edges[edge_id].estimated_flow
                    if obs_flow > 0:
                        rel_error = abs(est_flow - obs_flow) / obs_flow
                        errors.append(rel_error)
            
            if errors:
                mean_error = np.mean(errors)
                print(f"    - 平均相对误差: {mean_error*100:.1f}%")
        
        return routes
    
    @staticmethod
    def calculate_flow_distribution_lse(network: TrafficNetwork,
                                        observed_flows: Dict[str, float]) -> List[Route]:
        """
        基于非负最小二乘法计算OD流量分配
        
        核心思想：
        1. 构建路径-边关联矩阵 A: A[i,j] = 1 if 路径j经过边i, else 0
        2. 观测流量向量 b: b[i] = edge_i的观测流量
        3. 求解非负最小二乘: min ||Ax - b||² s.t. x >= 0
        4. x 就是各OD对的流量
        
        参数:
            network: 交通网络
            observed_flows: 观测流量 {edge_id: flow}
        
        返回:
            routes: 路由列表及其流量
        """
        print("正在使用非负最小二乘法计算OD矩阵")
        print(f"  - 观测边数: {len(observed_flows)}")
        
        # 1. 初始化：记录观测流量
        total_observed_flow = 0
        for edge_id, flow in observed_flows.items():
            if edge_id in network.edges:
                network.edges[edge_id].observed_flow = flow
                total_observed_flow += flow
        
        print(f"  - 总观测流量: {total_observed_flow:.0f} 辆/小时")
        print(f"  - OD对数量: {len(network.od_pairs)}")
        
        # 2. 为每个OD对计算路径
        print(f"  - 计算所有OD对的路径")
        od_paths = []
        for idx, (origin, dest) in enumerate(network.od_pairs, 1):
            if idx % 500 == 0:
                print(f"    路径计算进度: {idx}/{len(network.od_pairs)}")
            
            path_edges = RouteCalculator.dijkstra_shortest_path(network, origin, dest)
            if path_edges:
                od_paths.append({
                    'origin': origin,
                    'destination': dest,
                    'edges': path_edges
                })
        
        print(f"  - 成功计算 {len(od_paths)} 条路径")
        
        if len(od_paths) == 0:
            print("  ✗ 没有有效路径，无法计算")
            return []
        
        # 3. 构建路径-边关联矩阵 A 和观测流量向量 b
        # 只考虑有观测流量的边
        observed_edges = [eid for eid in observed_flows.keys() if eid in network.edges]
        edge_to_idx = {eid: i for i, eid in enumerate(observed_edges)}
        
        n_edges = len(observed_edges)
        n_paths = len(od_paths)
        
        print(f"  - 构建矩阵: {n_edges} 条边 × {n_paths} 条路径")
        
        # 使用稀疏矩阵存储（大多数元素为0）
        A = np.zeros((n_edges, n_paths))
        b = np.zeros(n_edges)
        
        # 填充矩阵 A
        for j, path_info in enumerate(od_paths):
            for edge in path_info['edges']:
                if edge.id in edge_to_idx:
                    i = edge_to_idx[edge.id]
                    A[i, j] = 1  # 路径j经过边i
        
        # 填充向量 b
        for i, edge_id in enumerate(observed_edges):
            b[i] = observed_flows[edge_id]
        
        # 4. 求解非负最小二乘: min ||Ax - b||² s.t. x >= 0
        print(f"  - 求解非负最小二乘问题")
        
        try:
            from scipy.optimize import nnls
            
            # nnls 返回 (solution, residual)
            x, residual = nnls(A, b)
            
            print(f"  - 求解完成，残差: {np.sqrt(residual):.2f}")
            
        except ImportError:
            # 如果没有 scipy，使用普通最小二乘（可能有负值）
            print("  - 警告: scipy不可用，使用普通最小二乘（可能产生负值）")
            x, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            # 截断负值
            x = np.maximum(x, 0)
        
        # 5. 创建路由并分配流量
        routes = []
        for j, path_info in enumerate(od_paths):
            flow = x[j]
            
            if flow > 0.01:  # 只保留有意义的流量（>0.01）
                route = Route(f'route_{j}', path_info['edges'], flow)
                routes.append(route)
                
                # 更新边的估计流量
                for edge in path_info['edges']:
                    edge.estimated_flow += flow
                    edge.routes.append(route)
        
        network.routes = routes
        
        # 6. 输出统计信息
        total_allocated_flow = sum(r.flow for r in routes)
        print(f"  ✓ OD矩阵计算完成")
        print(f"    - 有效路由: {len(routes)}/{len(od_paths)}")
        print(f"    - 总分配流量: {total_allocated_flow:.0f} 辆/小时")
        print(f"    - 平均OD流量: {total_allocated_flow/len(routes):.1f} 辆/小时" if routes else "")
        
        # 7. 计算拟合度
        if observed_flows:
            errors = []
            for edge_id, obs_flow in observed_flows.items():
                if edge_id in network.edges:
                    est_flow = network.edges[edge_id].estimated_flow
                    if obs_flow > 0:
                        rel_error = abs(est_flow - obs_flow) / obs_flow
                        errors.append(rel_error)
            
            if errors:
                mean_error = np.mean(errors)
                print(f"    - 平均相对误差: {mean_error*100:.1f}%")
        
        return routes
    
    @staticmethod
    def optimize_flow_assignment(network: TrafficNetwork,
                                observed_flows: Dict[str, float],
                                max_iterations: int = 100):
        """
        迭代优化流量分配
        
        使用启发式算法调整路由流量，使其更符合观测值
        """
        print("正在优化流量分配")
        
        # TODO: 实现迭代优化算法
        # 1. 计算当前分配与观测的差异
        # 2. 调整流量分配以减小差异
        # 3. 重复直到收敛
        
        print("  - 优化完成（占位实现）")


# ==================== 6. 可视化模块 ====================

class Visualizer:
    """可视化工具"""
    
    @staticmethod
    def plot_network_topology(network: TrafficNetwork, output_path: str):
        """
        绘制网络拓扑图
        
        使用matplotlib或networkx绘制
        """
        print(f"正在生成网络拓扑图: {output_path}")
        
        try:
            import networkx as nx
            
            # 创建networkx图
            G = nx.DiGraph()
            
            # 添加节点
            for node in network.nodes.values():
                G.add_node(node.id, pos=node.coord if node.coord else (0, 0))
            
            # 添加边
            for edge in network.edges.values():
                G.add_edge(edge.from_node.id, edge.to_node.id, 
                          label=edge.id, flow=edge.estimated_flow)
            
            # 绘制
            fig, ax = plt.subplots(figsize=(16, 12))
            
            pos = nx.get_node_attributes(G, 'pos')
            if not pos or all(v == (0, 0) for v in pos.values()):
                pos = nx.spring_layout(G, k=2, iterations=50)
            
            # 绘制边
            nx.draw_networkx_edges(G, pos, ax=ax, 
                                  edge_color='gray', 
                                  arrows=True, 
                                  arrowsize=10,
                                  alpha=0.6)
            
            # 绘制节点（区分OD候选节点、信号灯节点、普通节点）
            node_colors = []
            node_sizes = []
            for n in G.nodes():
                node = network.nodes[n]
                if node.is_od_candidate:
                    node_colors.append('red')  # OD候选节点：红色
                    node_sizes.append(400)
                elif node.has_traffic_light:
                    node_colors.append('orange')  # 信号灯节点：橙色
                    node_sizes.append(250)
                else:
                    node_colors.append('lightblue')  # 普通节点：浅蓝色
                    node_sizes.append(150)
            
            nx.draw_networkx_nodes(G, pos, ax=ax,
                                  node_color=node_colors,
                                  node_size=node_sizes,
                                  alpha=0.8)
            
            # 绘制节点标签（只标记OD候选节点）
            od_labels = {n: n for n in G.nodes() if network.nodes[n].is_od_candidate}
            nx.draw_networkx_labels(G, pos, labels=od_labels, ax=ax, font_size=6)
            
            # 添加图例
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], marker='o', color='w', markerfacecolor='red', 
                      markersize=12, label='OD Candidates'),
                Line2D([0], [0], marker='o', color='w', markerfacecolor='orange', 
                      markersize=10, label='Traffic Light'),
                Line2D([0], [0], marker='o', color='w', markerfacecolor='lightblue', 
                      markersize=8, label='Normal Node')
            ]
            ax.legend(handles=legend_elements, loc='upper right')
            
            # 统计信息
            num_od = sum(1 for n in network.nodes.values() if n.is_od_candidate)
            num_tls = sum(1 for n in network.nodes.values() if n.has_traffic_light)
            title = f'Network Topology\n{len(network.nodes)} nodes ({num_tls} TLS), {len(network.edges)} edges, {num_od} OD candidates'
            
            ax.set_title(title, fontsize=14)
            ax.axis('off')
            
            # 保存图片（抑制字体警告）
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                plt.tight_layout()
                plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"  - 拓扑图已保存")
            
        except ImportError as e:
            print(f"  - 跳过绘图（缺少依赖: {e}）")
    
    @staticmethod
    def plot_od_matrix(network: TrafficNetwork, output_path: str):
        """
        绘制OD矩阵热力图
        """
        print(f"正在生成OD矩阵图: {output_path}")
        
        # 检查是否有OD数据
        if len(network.od_pairs) == 0:
            print(f"  - 跳过（无OD对数据）")
            return
        
        try:
            import seaborn as sns
            
            # 构建OD矩阵
            od_nodes = sorted(set([o.id for o, d in network.od_pairs] + 
                                 [d.id for o, d in network.od_pairs]))
            n = len(od_nodes)
            
            if n == 0:
                print(f"  - 跳过（无OD节点）")
                return
            
            node_idx = {nid: i for i, nid in enumerate(od_nodes)}
            
            od_matrix = np.zeros((n, n))
            
            for route in network.routes:
                if route.origin and route.destination:
                    i = node_idx.get(route.origin.id, -1)
                    j = node_idx.get(route.destination.id, -1)
                    if i >= 0 and j >= 0:
                        od_matrix[i, j] += route.flow
            
            # 绘制热力图
            fig, ax = plt.subplots(figsize=(12, 10))
            sns.heatmap(od_matrix, 
                       xticklabels=od_nodes,
                       yticklabels=od_nodes,
                       cmap='YlOrRd',
                       ax=ax,
                       cbar_kws={'label': 'Flow (vehicles/hour)'})
            
            ax.set_title('OD Matrix', fontsize=14)
            ax.set_xlabel('Destination')
            ax.set_ylabel('Origin')
            
            # 保存图片（抑制字体警告）
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                plt.tight_layout()
                plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"  - OD矩阵图已保存")
            
        except ImportError as e:
            print(f"  - 跳过绘图（缺少依赖: {e}）")
    
    @staticmethod
    def plot_route_frequency(network: TrafficNetwork, output_path: str):
        """
        绘制边流量热力图：统计每条边上叠加的路径总值，染色显示（多=红色，少=蓝色）
        """
        print(f"正在生成路径流量热力图: {output_path}")
        
        try:
            # 统计每条边的总流量（叠加所有经过的路径）
            edge_flow_sum = {}
            for edge in network.edges.values():
                edge_flow_sum[edge.id] = 0
            
            # 叠加路径流量
            for route in network.routes:
                for edge in route.edges:
                    edge_flow_sum[edge.id] += route.flow
            
            # 更新边的estimated_flow
            for edge_id, flow in edge_flow_sum.items():
                if edge_id in network.edges:
                    network.edges[edge_id].estimated_flow = flow
            
            # 准备可视化数据
            flows = list(edge_flow_sum.values())
            if not flows or max(flows) == 0:
                print(f"  - 跳过（无流量数据）")
                return
            
            # 归一化流量用于颜色映射
            norm = Normalize(vmin=min(flows), vmax=max(flows))
            cmap = cm.RdYlBu_r  # 红色=多，蓝色=少
            
            # 绘制网络拓扑 + 流量热力图
            fig, ax = plt.subplots(figsize=(16, 14))
            
            # 绘制边（按流量染色）
            for edge in network.edges.values():
                from_node = edge.from_node
                to_node = edge.to_node
                
                if from_node.coord and to_node.coord:
                    flow = edge_flow_sum.get(edge.id, 0)
                    color = cmap(norm(flow))
                    
                    # 绘制边
                    ax.plot([from_node.coord[0], to_node.coord[0]],
                           [from_node.coord[1], to_node.coord[1]],
                           color=color, linewidth=2, alpha=0.7, zorder=1)
            
            # 绘制节点
            for node in network.nodes.values():
                if node.coord:
                    if node.is_od_candidate:
                        color = 'red'
                        size = 80
                    elif node.has_traffic_light:
                        color = 'orange'
                        size = 50
                    else:
                        color = 'lightblue'
                        size = 30
                    
                    ax.scatter(node.coord[0], node.coord[1], 
                             c=color, s=size, alpha=0.8, zorder=2, edgecolors='black', linewidth=0.5)
            
            # 添加颜色条
            sm = cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('Flow (vehicles/hour)', fontsize=12)
            
            ax.set_title('Route Flow Heatmap\n(Red=High Flow, Blue=Low Flow)', fontsize=14)
            ax.set_aspect('equal')
            ax.axis('off')  # 关闭坐标轴
            
            # 添加统计信息
            stats_text = f'Total Routes: {len(network.routes)}\n'
            stats_text += f'Flow Range: [{min(flows):.0f}, {max(flows):.0f}]\n'
            stats_text += f'Avg Flow: {np.mean(flows):.0f}'
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   fontsize=10, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
            
            # 保存图片（抑制字体警告）
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                plt.tight_layout()
                plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"  - 路径流量热力图已保存")
            
        except ImportError as e:
            print(f"  - 跳过绘图（缺少依赖: {e}）")
    
    @staticmethod
    def plot_error_heatmap(network: TrafficNetwork, flow_data: Dict[str, float], output_path: str):
        """
        绘制相对误差热力图：对比观测流量和估计流量
        
        颜色编码：
        - 红色：估计偏大（≥20%）
        - 白色：误差在±20%以内
        - 蓝色：估计偏小（≤-20%）
        """
        print(f"正在生成相对误差热力图: {output_path}")
        
        try:
            # 1. 收集有观测流量的边的误差信息
            error_data = []
            
            for edge in network.edges.values():
                if edge.observed_flow is not None and edge.observed_flow > 0:
                    estimated = edge.estimated_flow
                    observed = edge.observed_flow
                    
                    # 相对误差: (estimated - observed) / observed
                    rel_error = (estimated - observed) / observed
                    
                    error_data.append({
                        'edge': edge,
                        'observed': observed,
                        'estimated': estimated,
                        'rel_error': rel_error
                    })
            
            if not error_data:
                print(f"  - 跳过（无观测数据）")
                return
            
            print(f"  - 有观测数据的边: {len(error_data)}")
            
            # 2. 统计误差分布
            errors = [d['rel_error'] for d in error_data]
            overestimated = sum(1 for e in errors if e > 0.2)  # 高估>20%
            underestimated = sum(1 for e in errors if e < -0.2)  # 低估>20%
            accurate = len(errors) - overestimated - underestimated
            
            print(f"  - 误差分布: 高估{overestimated}条, 准确{accurate}条, 低估{underestimated}条")
            
            # 3. 准备节点坐标
            node_positions = {}
            for node in network.nodes.values():
                if node.coord:
                    node_positions[node.id] = node.coord
            
            # 4. 绘制热力图
            fig, ax = plt.subplots(figsize=(18, 14))
            
            # 颜色映射：蓝色（低估-20%）-> 白色（0%）-> 红色（高估+20%）
            # 使用RdBu_r: Red-Blue reversed (红正蓝负)
            norm = Normalize(vmin=-0.2, vmax=0.2)  # -20% to +20%
            cmap = cm.RdBu_r  # 红色=高估，蓝色=低估
            
            # 5. 绘制所有边（灰色背景）
            for edge in network.edges.values():
                if edge.from_node.coord and edge.to_node.coord:
                    from_pos = edge.from_node.coord
                    to_pos = edge.to_node.coord
                    ax.plot([from_pos[0], to_pos[0]],
                           [from_pos[1], to_pos[1]],
                           color='lightgray', linewidth=0.5, alpha=0.3, zorder=1)
            
            # 6. 绘制有误差数据的边（按误差染色）
            for data in error_data:
                edge = data['edge']
                rel_error = data['rel_error']
                
                if edge.from_node.coord and edge.to_node.coord:
                    from_pos = edge.from_node.coord
                    to_pos = edge.to_node.coord
                    
                    # 限制误差范围到[-0.2, 0.2]以便显示
                    clamped_error = np.clip(rel_error, -0.2, 0.2)
                    color = cmap(norm(clamped_error))
                    
                    # 误差越大，线条越粗
                    linewidth = 1.0 + abs(rel_error) * 2
                    linewidth = min(linewidth, 4.0)  # 最大4
                    
                    ax.plot([from_pos[0], to_pos[0]],
                           [from_pos[1], to_pos[1]],
                           color=color, linewidth=linewidth, alpha=0.8, zorder=2)
            
            # 7. 绘制节点
            for node in network.nodes.values():
                if node.coord:
                    if node.is_od_candidate:
                        color = 'black'
                        size = 60
                        alpha = 0.6
                    else:
                        color = 'gray'
                        size = 20
                        alpha = 0.4
                    
                    ax.scatter(node.coord[0], node.coord[1], 
                             c=color, s=size, alpha=alpha, zorder=3, 
                             edgecolors='white', linewidth=0.5)
            
            # 8. 添加颜色条
            sm = cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('Relative Error (Estimated - Observed) / Observed', 
                          rotation=270, labelpad=25, fontsize=11)
            
            # 设置刻度标签
            cbar.ax.set_yticks([-0.2, -0.1, 0, 0.1, 0.2])
            cbar.ax.set_yticklabels(['-20%', '-10%', '0%', '+10%', '+20%'])
            
            # 9. 标题和样式
            ax.set_title('Flow Estimation Error Heatmap\n(Red=Overestimated, Blue=Underestimated)', 
                        fontsize=14, fontweight='bold', pad=20)
            ax.axis('off')
            ax.set_aspect('equal')
            
            # 10. 添加统计信息
            mean_error = np.mean(errors)
            mean_abs_error = np.mean([abs(e) for e in errors])
            stats_text = f'Total Edges: {len(error_data)}\n'
            stats_text += f'Overestimated (>20%): {overestimated}\n'
            stats_text += f'Accurate (±20%): {accurate}\n'
            stats_text += f'Underestimated (<-20%): {underestimated}\n'
            stats_text += f'Mean Error: {mean_error*100:+.1f}%\n'
            stats_text += f'Mean Abs Error: {mean_abs_error*100:.1f}%'
            
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   fontsize=10, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            # 11. 保存图片
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                plt.tight_layout()
                plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"  - 相对误差热力图已保存")
            
        except ImportError as e:
            print(f"  - 跳过绘图（缺少依赖: {e}）")
        except Exception as e:
            print(f"  - 绘图出错: {e}")
    
    @staticmethod
    def generate_html_report(network: TrafficNetwork, output_path: str):
        """
        生成HTML交互式报告
        """
        print(f"正在生成HTML报告: {output_path}")
        
        # TODO: 使用plotly生成交互式图表
        
        stats = network.get_statistics()
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Traffic Flow Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }}
        .stat-card {{ background: #f9f9f9; padding: 15px; border-radius: 5px; border-left: 4px solid #4CAF50; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #4CAF50; }}
        .stat-label {{ color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>交通流量反演分析报告</h1>
        
        <h2>网络统计</h2>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{stats['num_nodes']}</div>
                <div class="stat-label">节点数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['num_edges']}</div>
                <div class="stat-label">边数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['num_od_pairs']}</div>
                <div class="stat-label">OD对数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['num_routes']}</div>
                <div class="stat-label">路由数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['total_flow']:.0f}</div>
                <div class="stat-label">总流量 (车/小时)</div>
            </div>
        </div>
        
        <h2>路由详情</h2>
        <p>生成了 {len(network.routes)} 条路由...</p>
        
        <!-- TODO: 添加交互式图表 -->
    </div>
</body>
</html>
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"  - HTML报告已保存")


# ==================== 7. 输出模块 ====================

class RouteExporter:
    """路由导出器"""
    
    @staticmethod
    def export_sumo_routes(network: TrafficNetwork, 
                          output_path: str,
                          begin_time: int = 0,
                          end_time: int = 3600):
        """
        导出SUMO路由文件格式
        """
        print(f"正在导出SUMO路由文件: {output_path}")
        
        root = ET.Element('routes')
        root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        root.set('xsi:noNamespaceSchemaLocation', 
                'http://sumo.dlr.de/xsd/routes_file.xsd')
        
        # 车辆类型
        vtype = ET.SubElement(root, 'vType')
        vtype.set('id', 'car')
        vtype.set('accel', '2.6')
        vtype.set('decel', '4.5')
        vtype.set('sigma', '0.5')
        vtype.set('length', '5')
        vtype.set('maxSpeed', '50')
        
        # 路由定义
        for route in network.routes:
            if route.flow <= 0:
                continue
            
            # route元素
            route_elem = ET.SubElement(root, 'route')
            route_elem.set('id', route.id)
            route_elem.set('edges', ' '.join(route.get_edge_ids()))
            
            # flow元素
            flow_elem = ET.SubElement(root, 'flow')
            flow_elem.set('id', f'flow_{route.id}')
            flow_elem.set('type', 'car')
            flow_elem.set('route', route.id)
            flow_elem.set('number', str(int(route.flow)))
            flow_elem.set('begin', str(begin_time))
            flow_elem.set('end', str(end_time))
            flow_elem.set('departLane', 'best')
            flow_elem.set('departSpeed', 'max')
        
        # 写入文件
        tree = ET.ElementTree(root)
        ET.indent(tree, space='    ')
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        
        print(f"  - 导出 {len(network.routes)} 条路由")
    
    @staticmethod
    def export_od_matrix(network: TrafficNetwork, output_path: str):
        """导出OD矩阵为CSV"""
        print(f"正在导出OD矩阵: {output_path}")
        
        # 构建OD矩阵
        od_dict = defaultdict(lambda: defaultdict(float))
        
        for route in network.routes:
            if route.origin and route.destination:
                od_dict[route.origin.id][route.destination.id] += route.flow
        
        # 转换为DataFrame
        origins = sorted(od_dict.keys())
        destinations = sorted(set(d for origin_dests in od_dict.values() 
                                 for d in origin_dests.keys()))
        
        data = []
        for o in origins:
            row = [o]
            for d in destinations:
                row.append(od_dict[o].get(d, 0))
            data.append(row)
        
        df = pd.DataFrame(data, columns=['Origin'] + destinations)
        df.to_csv(output_path, index=False)
        
        print(f"  - OD矩阵已导出")


# ==================== 8. 主流程 ====================

class TrafficFlowInverter:
    """交通流量反演主程序"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.network = None
        self.flow_data = None
        
    def run_pipeline(self):
        """运行完整流程"""
        print("="*60)
        print("交通流量反演系统")
        print("="*60)
        
        visualize_only = self.config.get('visualize_only', False)
        skip_od = self.config.get('skip_od', False)
        skip_export = self.config.get('skip_export', False)
        
        # 1. 数据预处理
        if not visualize_only:
            print("\n[1/7] 数据预处理")
            self.preprocess_data()
        
        # 2. 构建网络拓扑
        print("\n[2/7] 构建网络拓扑")
        self.build_network()
        
        if visualize_only:
            # 仅可视化模式：只执行网络加载和可视化
            print("\n[模式] 仅可视化网络拓扑")
            
            if not skip_od:
                print("\n[3/7] 选择OD节点（用于标记）")
                self.select_od_nodes()
            
            print("\n[4/7] 生成可视化")
            self.generate_visualizations()
            
            print("\n" + "="*60)
            print("✓ 可视化完成！")
            print("="*60)
            return
        
        # 3. 选择OD节点
        print("\n[3/7] 选择OD节点")
        self.select_od_nodes()
        
        # 4. 计算路由
        print("\n[4/7] 计算路由")
        self.calculate_routes()
        
        # 5. 导出结果
        if not skip_export:
            print("\n[5/7] 导出结果")
            self.export_results()
        else:
            print("\n[5/7] 跳过导出")
        
        # 6. 生成可视化
        print("\n[6/7] 生成可视化")
        self.generate_visualizations()
        
        # 7. 生成报告
        if not skip_export:
            print("\n[7/7] 生成报告")
            self.generate_report()
        else:
            print("\n[7/7] 跳过报告")
        
        print("\n" + "="*60)
        print("✓ 完成！")
        print("="*60)
    
    def run_multi_hour_pipeline(self):
        """运行多时段处理流程"""
        print("="*60)
        print("交通流量反演系统 - 多时段处理")
        print("="*60)
        
        # 确定流量数据目录和时段数
        flow_dir = self.config.get('flow_dir')
        if not flow_dir and self.config.get('flow_csv'):
            # 如果只提供了单个文件，提取目录
            flow_dir = os.path.dirname(self.config['flow_csv'])
        
        if not flow_dir or not os.path.exists(flow_dir):
            print(f"错误: 流量数据目录不存在: {flow_dir}")
            return
        
        hours = self.config.get('hours', 1)
        output_dir = self.config.get('output_dir', 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n流量数据目录: {flow_dir}")
        print(f"处理时段数: {hours} 小时")
        print(f"输出目录: {output_dir}")
        
        # 1. 构建网络拓扑（只需一次）
        print("\n[1/4] 构建网络拓扑")
        self.build_network()
        
        # 2. 选择OD节点（只需一次）
        print("\n[2/4] 选择OD节点")
        self.select_od_nodes()
        
        # 3. 为每个时段分别处理
        print(f"\n[3/4] 处理各时段流量和路由")
        
        all_hourly_routes = []  # 存储所有时段的路由
        
        for hour in range(hours):
            print(f"\n--- 处理第 {hour} 小时 ---")
            
            # 3.1 加载该时段的流量数据
            flow_file = os.path.join(flow_dir, f'flow_hour_{hour}.csv')
            if not os.path.exists(flow_file):
                print(f"  警告: 流量文件不存在: {flow_file}，跳过该时段")
                continue
            
            print(f"  加载流量数据: {flow_file}")
            processor = FlowDataProcessor()
            df = processor.load_csv_data(flow_file)
            df = processor.clean_data(df)
            self.flow_data = processor.aggregate_flow(df)
            print(f"  - 流量边数: {len(self.flow_data)}")
            
            # 3.2 计算该时段的路由
            print(f"  计算路由...")
            self.calculate_routes()
            
            # 3.3 保存该时段的路由（用于合并）
            hourly_routes = []
            for route in self.network.routes:
                # 为每条路由记录时段信息
                hourly_routes.append({
                    'hour': hour,
                    'route': route,
                    'origin': route.origin.id,
                    'destination': route.destination.id,
                    'edges': [e.id for e in route.edges],
                    'flow': route.flow
                })
            all_hourly_routes.extend(hourly_routes)
            print(f"  - 生成路由数: {len(hourly_routes)}")
            
            # 3.4 生成该时段的可视化
            hour_output_dir = os.path.join(output_dir, f'hour_{hour}')
            os.makedirs(hour_output_dir, exist_ok=True)
            
            print(f"  生成可视化...")
            viz = Visualizer()
            
            # OD矩阵
            if len(self.network.od_pairs) > 0:
                viz.plot_od_matrix(
                    self.network,
                    os.path.join(hour_output_dir, 'od_matrix.png')
                )
            
            # 路由频率
            if len(self.network.routes) > 0:
                viz.plot_route_frequency(
                    self.network,
                    os.path.join(hour_output_dir, 'route_frequency.png')
                )
            
            # 误差热力图
            if len(self.network.routes) > 0 and self.flow_data and len(self.flow_data) > 0:
                Visualizer.plot_error_heatmap(
                    self.network,
                    self.flow_data,
                    os.path.join(hour_output_dir, 'error_heatmap.png')
                )
            
            print(f"  ✓ 第 {hour} 小时处理完成")
        
        # 4. 合并所有时段的路由并导出
        print(f"\n[4/4] 合并并导出所有时段路由")
        print(f"  总路由数: {len(all_hourly_routes)}")
        
        # 导出统一的路由文件
        self._export_multi_hour_routes(all_hourly_routes, output_dir)
        
        # 生成网络拓扑图（放在主输出目录）
        print(f"\n生成网络拓扑图...")
        viz = Visualizer()
        viz.plot_network_topology(
            self.network,
            os.path.join(output_dir, 'network_topology.png')
        )
        
        print("\n" + "="*60)
        print("✓ 多时段处理完成！")
        print(f"  - 处理时段数: {hours}")
        print(f"  - 总路由数: {len(all_hourly_routes)}")
        print(f"  - 输出目录: {output_dir}")
        print("="*60)
    
    def _export_multi_hour_routes(self, all_hourly_routes, output_dir):
        """导出多时段合并的路由文件"""
        route_file = os.path.join(output_dir, 'routes.rou.xml')
        
        with open(route_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ')
            f.write('xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">\n\n')
            
            # 统计信息
            total_vehicles = 0
            
            for i, route_info in enumerate(all_hourly_routes):
                hour = route_info['hour']
                route = route_info['route']
                edges = route_info['edges']
                flow = route_info['flow']
                
                # 跳过零流量路由
                if flow < 0.01:
                    continue
                
                # 定义路由
                route_id = f"route_h{hour}_{i}"
                f.write(f'    <route id="{route_id}" edges="{" ".join(edges)}"/>\n')
                
                # 生成车辆（按流量）
                # 将流量转换为车辆数（向上取整）
                num_vehicles = int(np.ceil(flow))
                
                # 在该小时内均匀分布出发时间
                hour_start = hour * 3600  # 小时转秒
                hour_end = (hour + 1) * 3600
                
                if num_vehicles > 0:
                    time_interval = 3600.0 / num_vehicles
                    for v in range(num_vehicles):
                        depart_time = hour_start + v * time_interval
                        veh_id = f"veh_h{hour}_r{i}_{v}"
                        f.write(f'    <vehicle id="{veh_id}" route="{route_id}" depart="{depart_time:.2f}"/>\n')
                        total_vehicles += 1
                
                f.write('\n')
            
            f.write('</routes>\n')
        
        print(f"  ✓ 路由文件已保存: {route_file}")
        print(f"  ✓ 总车辆数: {total_vehicles}")
    
    def preprocess_data(self):
        """数据预处理"""
        processor = FlowDataProcessor()
        
        # 加载CSV数据
        if 'flow_csv' in self.config and self.config['flow_csv']:
            df = processor.load_csv_data(self.config['flow_csv'])
            df = processor.clean_data(df)
            self.flow_data = processor.aggregate_flow(df)
        elif 'flow_excel' in self.config and self.config['flow_excel']:
            df = processor.load_csv_data(self.config['flow_excel'])
            df = processor.clean_data(df)
            self.flow_data = processor.aggregate_flow(df)
        else:
            print("  - 未提供流量数据，使用模拟数据")
            self.flow_data = {}
    
    def build_network(self):
        """构建网络"""
        builder = NetworkBuilder()
        
        if 'network_file' in self.config:
            self.network = builder.load_sumo_network(self.config['network_file'])
        else:
            print("  - 未提供路网文件，使用示例网络")
            self.network = builder.load_sumo_network('dummy.net.xml')
        
        # 保存网络
        cache_path = self.config.get('cache_dir', 'cache')
        os.makedirs(cache_path, exist_ok=True)
        builder.save_network(self.network, 
                           os.path.join(cache_path, 'network.pkl'))
    
    def select_od_nodes(self):
        """选择OD节点"""
        selector = ODSelector()
        
        strategy = self.config.get('od_strategy', 'traffic_light_density')
        max_pairs = self.config.get('max_od_pairs', 100)
        sampling_ratio = self.config.get('od_sampling_ratio', 0.5)
        min_distance_ratio = self.config.get('min_od_distance_ratio', 0.2)
        
        selector.select_od_nodes(self.network, 
                                max_od_pairs=max_pairs,
                                strategy=strategy,
                                sampling_ratio=sampling_ratio,
                                min_distance_ratio=min_distance_ratio)
    
    def calculate_routes(self):
        """计算路由"""
        calculator = RouteCalculator()
        
        # 使用基于观测流量的流量分配算法
        if self.flow_data and len(self.flow_data) > 0:
            print(f"使用观测流量数据（{len(self.flow_data)} 条边）")
            
            # 选择算法：median（中位数估计） 或 lse（最小二乘）
            algorithm = self.config.get('od_algorithm', 'median')
            
            if algorithm == 'lse':
                print("算法: 非负最小二乘法")
                calculator.calculate_flow_distribution_lse(self.network, self.flow_data)
            else:
                print("算法: 中位数估计")
                calculator.calculate_flow_distribution(self.network, self.flow_data)
        else:
            # 回退到简化版：统一初始化OD矩阵
            print("未提供观测流量，使用统一初始化")
            initial_flow = self.config.get('initial_flow', 100.0)
            calculator.calculate_routes_simple(self.network, initial_flow=initial_flow)
        
        # 可选：优化
        if self.config.get('optimize', False) and self.flow_data:
            calculator.optimize_flow_assignment(self.network, self.flow_data)
    
    def export_results(self):
        """导出结果"""
        exporter = RouteExporter()
        output_dir = self.config.get('output_dir', 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # 导出SUMO路由
        exporter.export_sumo_routes(
            self.network,
            os.path.join(output_dir, 'routes.rou.xml')
        )
        
        # 导出OD矩阵
        exporter.export_od_matrix(
            self.network,
            os.path.join(output_dir, 'od_matrix.csv')
        )
    
    def generate_visualizations(self):
        """生成可视化"""
        viz = Visualizer()
        output_dir = self.config.get('output_dir', 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # 网络拓扑（总是生成）
        viz.plot_network_topology(
            self.network,
            os.path.join(output_dir, 'network_topology.png')
        )
        
        # OD矩阵（仅当有OD对时生成）
        if len(self.network.od_pairs) > 0:
            viz.plot_od_matrix(
                self.network,
                os.path.join(output_dir, 'od_matrix.png')
            )
        else:
            print(f"  - 跳过OD矩阵图（无OD对数据）")
        
        # 路由频率（仅当有路由时生成）
        if len(self.network.routes) > 0:
            viz.plot_route_frequency(
                self.network,
                os.path.join(output_dir, 'route_frequency.png')
            )
        else:
            print(f"  - 跳过路由频率图（无路由数据）")
        
        # 相对误差热力图（仅当有路由和观测流量时生成）
        if len(self.network.routes) > 0 and self.flow_data and len(self.flow_data) > 0:
            viz.plot_error_heatmap(
                self.network,
                self.flow_data,
                os.path.join(output_dir, 'error_heatmap.png')
            )
        else:
            print(f"  - 跳过误差热力图（无观测流量或路由数据）")
    
    def generate_report(self):
        """生成报告"""
        viz = Visualizer()
        output_dir = self.config.get('output_dir', 'output')
        
        viz.generate_html_report(
            self.network,
            os.path.join(output_dir, 'report.html')
        )


# ==================== 9. 命令行接口 ====================

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='交通流量反演系统 - 从真实数据生成SUMO路由',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 单时段处理
  python traffic_flow_inverter.py \\
      --network network.net.xml \\
      --flow-data flow_hour_0.csv \\
      --output-dir output/
  
  # 多时段处理（自动读取flow_hour_0.csv, flow_hour_1.csv, ...）
  python traffic_flow_inverter.py \\
      --network network.net.xml \\
      --flow-dir flow_data/ \\
      --hours 3 \\
      --output-dir output/
  
  # 指定OD选择策略和算法
  python traffic_flow_inverter.py \\
      --network network.net.xml \\
      --flow-dir flow_data/ \\
      --hours 2 \\
      --od-strategy traffic_light_density \\
      --od-algorithm lse \\
      --output-dir output/
        """
    )
    
    parser.add_argument('-n', '--network', type=str,
                       help='SUMO路网文件 (.net.xml)')
    parser.add_argument('-f', '--flow-data', type=str,
                       help='流量数据文件 (.csv格式，包含edge_id和flow列) 或流量数据目录（包含flow_hour_*.csv文件）')
    parser.add_argument('--flow-dir', type=str,
                       help='流量数据目录（包含flow_hour_*.csv文件），优先级高于--flow-data')
    parser.add_argument('--hours', type=int, default=1,
                       help='总时段数（小时），默认: 1（仅处理第0小时）')
    parser.add_argument('-o', '--output-dir', type=str, default='output',
                       help='输出目录, 默认: output')
    parser.add_argument('--od-strategy', type=str, 
                       choices=['traffic_light_density'],
                       default='traffic_light_density',
                       help='OD节点选择策略（基于信号灯节点和密度）, 默认: traffic_light_density')
    parser.add_argument('--max-od-pairs', type=int, default=100,
                       help='最大OD对数量, 默认: 100（已废弃）')
    parser.add_argument('--od-sampling-ratio', type=float, default=0.5,
                       help='内部信号灯节点的采样比例, 默认: 0.5（50%%）')
    parser.add_argument('--min-od-distance-ratio', type=float, default=0.2,
                       help='最小OD距离比例（相对于地图尺度）, 默认: 0.2（20%%）')
    parser.add_argument('--initial-flow', type=float, default=100.0,
                       help='OD矩阵初始流量值, 默认: 100.0')
    parser.add_argument('--od-algorithm', type=str,
                       choices=['median', 'lse'],
                       default='median',
                       help='OD流量计算算法: median=中位数估计, lse=最小二乘法, 默认: median')
    parser.add_argument('--optimize', action='store_true',
                       help='启用流量分配优化')
    parser.add_argument('--config', type=str,
                       help='配置文件路径 (JSON)')
    parser.add_argument('--cache-dir', type=str, default='cache',
                       help='缓存目录, 默认: cache')
    parser.add_argument('--visualize-only', action='store_true',
                       help='仅进行网络加载和可视化，不计算路由')
    parser.add_argument('--skip-od', action='store_true',
                       help='跳过OD节点选择')
    parser.add_argument('--skip-export', action='store_true',
                       help='跳过结果导出（仅测试和可视化）')
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_arguments()
    
    # 构建配置
    if args.config:
        # 从配置文件加载
        with open(args.config, 'r') as f:
            config = json.load(f)
    else:
        # 确定流量数据路径
        flow_dir = args.flow_dir if args.flow_dir else None
        flow_data = args.flow_data if hasattr(args, 'flow_data') else None
        
        # 从命令行参数构建
        config = {
            'network_file': args.network,
            'flow_csv': flow_data,  # 单文件模式（向后兼容）
            'flow_dir': flow_dir,   # 多文件目录
            'hours': args.hours,    # 总时段数
            'output_dir': args.output_dir,
            'od_strategy': args.od_strategy,
            'max_od_pairs': args.max_od_pairs,
            'od_sampling_ratio': args.od_sampling_ratio,
            'min_od_distance_ratio': args.min_od_distance_ratio,
            'initial_flow': args.initial_flow,
            'od_algorithm': args.od_algorithm,
            'optimize': args.optimize,
            'cache_dir': args.cache_dir,
            'visualize_only': args.visualize_only,
            'skip_od': args.skip_od,
            'skip_export': args.skip_export
        }
    
    # 运行主流程
    inverter = TrafficFlowInverter(config)
    
    # 判断是单时段还是多时段处理
    if config.get('flow_dir') or config.get('hours', 1) > 1:
        inverter.run_multi_hour_pipeline()
    else:
        inverter.run_pipeline()


if __name__ == '__main__':
    main()

