#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从SUMO路由文件提取流量数据
用于生成测试样例：统计每个信号灯路口各边的每小时流量
"""

import os
import sys
import xml.etree.ElementTree as ET
import argparse
from collections import defaultdict
import pandas as pd
import json
import warnings
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import Normalize
import numpy as np

# 过滤matplotlib弃用警告
warnings.filterwarnings('ignore', category=DeprecationWarning, module='matplotlib')

# 添加SUMO工具路径
if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
    import sumolib
else:
    sys.exit("请设置环境变量 SUMO_HOME")


class FlowExtractor:
    """从路由文件提取流量"""
    
    def __init__(self, net_file, route_file):
        """
        参数:
            net_file: SUMO网络文件 (.net.xml)
            route_file: SUMO路由文件 (.rou.xml)
        """
        self.net_file = net_file
        self.route_file = route_file
        self.net = None
        self.tls_edges = set()  # 与信号灯直接相连的边
        self.hourly_flow = defaultdict(lambda: defaultdict(int))  # 按小时统计：{hour: {edge_id: count}}
        self.total_edge_flow = defaultdict(int)  # 每条边的总流量（所有小时）
        self.simulation_duration = 0  # 仿真总时长（秒）
        
    def load_network(self):
        """加载网络并识别信号灯边"""
        print(f"正在加载网络: {self.net_file}")
        self.net = sumolib.net.readNet(self.net_file)
        
        # 识别所有信号灯节点
        tls_nodes = set()
        for tls in self.net.getTrafficLights():
            # 信号灯的ID通常就是它所在节点的ID
            tls_nodes.add(tls.getID())
        
        print(f"  - 发现 {len(tls_nodes)} 个信号灯节点")
        
        # 找到所有与信号灯节点直接相连的边（入边）
        for edge in self.net.getEdges():
            # 跳过内部边
            if edge.isSpecial() or edge.getFunction() == 'internal':
                continue
            
            # 检查该边的终点是否是信号灯节点
            to_node = edge.getToNode()
            if to_node.getID() in tls_nodes:
                self.tls_edges.add(edge.getID())
        
        print(f"  - 识别 {len(self.tls_edges)} 条与信号灯相连的边（入边）")
        
    def extract_flows(self):
        """从路由文件提取流量（按小时统计）"""
        print(f"\n正在提取流量数据: {self.route_file}")
        
        # 解析路由文件
        tree = ET.parse(self.route_file)
        root = tree.getroot()
        
        total_vehicles = 0
        processed_vehicles = 0
        max_depart_time = 0
        
        # 遍历所有车辆
        for vehicle in root.findall('vehicle'):
            total_vehicles += 1
            
            # 获取出发时间
            depart_str = vehicle.get('depart', '0')
            try:
                depart_time = float(depart_str)
            except ValueError:
                # 如果depart是"triggered"等特殊值，跳过
                continue
            
            max_depart_time = max(max_depart_time, depart_time)
            
            # 计算所属小时（向下取整）
            hour = int(depart_time // 3600)
            
            # 获取路由
            route_elem = vehicle.find('route')
            if route_elem is None:
                continue
            
            edges_str = route_elem.get('edges', '')
            if not edges_str:
                continue
            
            edges = edges_str.split()
            
            # 统计该车辆经过的所有与信号灯相连的边
            for edge_id in edges:
                if edge_id in self.tls_edges:
                    self.hourly_flow[hour][edge_id] += 1
                    self.total_edge_flow[edge_id] += 1
            
            processed_vehicles += 1
            
            if processed_vehicles % 1000 == 0:
                print(f"  - 已处理 {processed_vehicles}/{total_vehicles} 辆车")
        
        self.simulation_duration = max_depart_time
        num_hours = int(max_depart_time // 3600) + 1
        
        print(f"\n✓ 流量提取完成")
        print(f"  - 总车辆数: {total_vehicles}")
        print(f"  - 有效车辆: {processed_vehicles}")
        print(f"  - 仿真时长: {max_depart_time:.0f}秒 ({num_hours}小时)")
        print(f"  - 统计时间段: {len(self.hourly_flow)} 个小时")
        
        # 统计有流量的边数
        all_edges_with_flow = set()
        for hour_data in self.hourly_flow.values():
            all_edges_with_flow.update(hour_data.keys())
        print(f"  - 有流量的边: {len(all_edges_with_flow)}")
        
    
    def export_flows(self, output_dir, export_format='simple'):
        """
        导出流量数据（简洁格式）
        
        输出文件:
            - flow_hour_0.csv: 第0小时的流量 (edge_id, flow)
            - flow_hour_1.csv: 第1小时的流量
            - ...
            - flow_summary.txt: 简单统计摘要
        """
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n正在导出流量数据到: {output_dir}")
        
        # 按每个小时分别导出简洁的CSV文件
        total_flow_per_edge = defaultdict(int)
        
        for hour in sorted(self.hourly_flow.keys()):
            # 简洁格式：只有 edge_id 和 flow 两列
            flow_data = []
            for edge_id, count in sorted(self.hourly_flow[hour].items()):
                flow_data.append({
                    'edge_id': edge_id,
                    'flow': count
                })
                total_flow_per_edge[edge_id] += count
            
            # 导出该小时的CSV
            csv_file = os.path.join(output_dir, f'flow_hour_{hour}.csv')
            df = pd.DataFrame(flow_data)
            df.to_csv(csv_file, index=False)
            print(f"  ✓ 第{hour}小时: {csv_file} ({len(df)} 条边)")
        
        # 导出简单的统计摘要
        summary_file = os.path.join(output_dir, 'flow_summary.txt')
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("流量数据摘要\n")
            f.write("="*40 + "\n\n")
            f.write(f"统计时段: {len(self.hourly_flow)} 小时\n")
            f.write(f"有流量的边: {len(total_flow_per_edge)} 条\n")
            f.write(f"总流量: {sum(total_flow_per_edge.values())} 辆\n\n")
            
            f.write("各小时流量:\n")
            for hour in sorted(self.hourly_flow.keys()):
                hour_total = sum(self.hourly_flow[hour].values())
                f.write(f"  第{hour}小时: {hour_total} 辆\n")
        
        print(f"  ✓ 摘要: {summary_file}")
        print(f"\n总计:")
        print(f"  - 时段数: {len(self.hourly_flow)}")
        print(f"  - 有流量的边: {len(total_flow_per_edge)}")
        print(f"  - 总流量: {sum(total_flow_per_edge.values())}")
    
    def visualize_flow_heatmap(self, output_dir):
        """
        可视化原始路由的流量热力图
        
        参数:
            output_dir: 输出目录
        """
        print(f"\n正在生成流量热力图...")
        
        # 1. 收集所有节点坐标和边信息
        node_positions = {}
        edge_info = {}
        
        for node in self.net.getNodes():
            node_id = node.getID()
            x, y = node.getCoord()
            node_positions[node_id] = (x, y)
        
        for edge in self.net.getEdges():
            if edge.isSpecial() or edge.getFunction() == 'internal':
                continue
            
            edge_id = edge.getID()
            from_node = edge.getFromNode().getID()
            to_node = edge.getToNode().getID()
            
            if from_node in node_positions and to_node in node_positions:
                edge_info[edge_id] = {
                    'from': from_node,
                    'to': to_node,
                    'flow': self.total_edge_flow.get(edge_id, 0)
                }
        
        # 2. 计算流量统计
        flows = [info['flow'] for info in edge_info.values() if info['flow'] > 0]
        if not flows:
            print("  警告: 没有流量数据，跳过可视化")
            return
        
        max_flow = max(flows)
        min_flow = min(flows)
        avg_flow = np.mean(flows)
        
        print(f"  - 有流量的边: {len(flows)}/{len(edge_info)}")
        print(f"  - 流量范围: [{min_flow:.0f}, {max_flow:.0f}]")
        print(f"  - 平均流量: {avg_flow:.1f}")
        
        # 3. 绘制热力图
        fig, ax = plt.subplots(figsize=(16, 14))
        
        # 颜色映射：红色(高流量) -> 黄色 -> 蓝色(低流量)
        norm = Normalize(vmin=min_flow, vmax=max_flow)
        cmap = plt.get_cmap('RdYlBu_r')
        
        # 先绘制无流量的边（灰色）
        for edge_id, info in edge_info.items():
            if info['flow'] == 0:
                from_pos = node_positions[info['from']]
                to_pos = node_positions[info['to']]
                ax.plot([from_pos[0], to_pos[0]], 
                       [from_pos[1], to_pos[1]], 
                       'lightgray', linewidth=0.5, alpha=0.3, zorder=1)
        
        # 绘制有流量的边（按流量染色）
        for edge_id, info in edge_info.items():
            if info['flow'] > 0:
                from_pos = node_positions[info['from']]
                to_pos = node_positions[info['to']]
                
                color = cmap(norm(info['flow']))
                
                ax.plot([from_pos[0], to_pos[0]], 
                       [from_pos[1], to_pos[1]], 
                       color=color, linewidth=2, alpha=0.7, zorder=2)
        
        # 绘制节点
        for node_id, (x, y) in node_positions.items():
            ax.scatter(x, y, c='lightblue', s=30, alpha=0.8, zorder=3, 
                      edgecolors='black', linewidth=0.5)
        
        # 添加颜色条
        sm = cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label('Flow (vehicles)', rotation=270, labelpad=20, fontsize=12)
        
        # 设置标题和样式
        ax.set_title('Original Route Flow Heatmap', fontsize=16, fontweight='bold', pad=20)
        ax.axis('off')
        ax.set_aspect('equal')
        
        # 添加统计信息
        stats_text = f'Total Flow: {sum(flows):.0f} veh\n'
        stats_text += f'Edges with Flow: {len(flows)}\n'
        stats_text += f'Flow Range: [{min_flow:.0f}, {max_flow:.0f}]\n'
        stats_text += f'Average Flow: {avg_flow:.1f}'
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=10, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # 保存图片（抑制字体警告）
        output_file = os.path.join(output_dir, 'original_route_frequency.png')
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            plt.tight_layout()
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"  ✓ 热力图已保存: {output_file}")
    
    def visualize_hourly_flow_heatmap(self, output_dir, hour):
        """
        可视化指定小时的流量热力图
        
        参数:
            output_dir: 输出目录
            hour: 小时数（0, 1, 2, ...）
        """
        if hour not in self.hourly_flow:
            print(f"  警告: 第{hour}小时没有流量数据")
            return
        
        print(f"\n正在生成第{hour}小时的流量热力图...")
        
        # 1. 收集所有节点坐标和边信息
        node_positions = {}
        edge_info = {}
        
        for node in self.net.getNodes():
            node_id = node.getID()
            x, y = node.getCoord()
            node_positions[node_id] = (x, y)
        
        for edge in self.net.getEdges():
            if edge.isSpecial() or edge.getFunction() == 'internal':
                continue
            
            edge_id = edge.getID()
            from_node = edge.getFromNode().getID()
            to_node = edge.getToNode().getID()
            
            if from_node in node_positions and to_node in node_positions:
                edge_info[edge_id] = {
                    'from': from_node,
                    'to': to_node,
                    'flow': self.hourly_flow[hour].get(edge_id, 0)
                }
        
        # 2. 计算流量统计
        flows = [info['flow'] for info in edge_info.values() if info['flow'] > 0]
        if not flows:
            print(f"  警告: 第{hour}小时没有流量数据，跳过可视化")
            return
        
        max_flow = max(flows)
        min_flow = min(flows)
        avg_flow = np.mean(flows)
        
        print(f"  - 有流量的边: {len(flows)}/{len(edge_info)}")
        print(f"  - 流量范围: [{min_flow:.0f}, {max_flow:.0f}]")
        print(f"  - 平均流量: {avg_flow:.1f}")
        
        # 3. 绘制热力图
        fig, ax = plt.subplots(figsize=(16, 14))
        
        # 颜色映射：红色(高流量) -> 黄色 -> 蓝色(低流量)
        norm = Normalize(vmin=min_flow, vmax=max_flow)
        cmap = plt.get_cmap('RdYlBu_r')
        
        # 先绘制无流量的边（灰色）
        for edge_id, info in edge_info.items():
            if info['flow'] == 0:
                from_pos = node_positions[info['from']]
                to_pos = node_positions[info['to']]
                ax.plot([from_pos[0], to_pos[0]], 
                       [from_pos[1], to_pos[1]], 
                       'lightgray', linewidth=0.5, alpha=0.3, zorder=1)
        
        # 绘制有流量的边（按流量染色）
        for edge_id, info in edge_info.items():
            if info['flow'] > 0:
                from_pos = node_positions[info['from']]
                to_pos = node_positions[info['to']]
                
                color = cmap(norm(info['flow']))
                
                ax.plot([from_pos[0], to_pos[0]], 
                       [from_pos[1], to_pos[1]], 
                       color=color, linewidth=2, alpha=0.7, zorder=2)
        
        # 绘制节点
        for node_id, (x, y) in node_positions.items():
            ax.scatter(x, y, c='lightblue', s=30, alpha=0.8, zorder=3, 
                      edgecolors='black', linewidth=0.5)
        
        # 添加颜色条
        sm = cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label('Flow (veh/h)', rotation=270, labelpad=20, fontsize=12)
        
        # 设置标题和样式
        ax.set_title(f'Original Route Flow Heatmap - Hour {hour}', fontsize=16, fontweight='bold', pad=20)
        ax.axis('off')
        ax.set_aspect('equal')
        
        # 添加统计信息
        stats_text = f'Time: Hour {hour}\n'
        stats_text += f'Total Flow: {sum(flows):.0f} veh\n'
        stats_text += f'Edges with Flow: {len(flows)}\n'
        stats_text += f'Flow Range: [{min_flow:.0f}, {max_flow:.0f}]\n'
        stats_text += f'Average Flow: {avg_flow:.1f}'
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=10, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # 保存图片（抑制字体警告）
        output_file = os.path.join(output_dir, f'original_route_frequency_hour_{hour}.png')
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            plt.tight_layout()
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"  ✓ 热力图已保存: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='从SUMO路由文件提取信号灯路口流量数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 提取流量数据并生成每小时的热力图
  python extract_flow_from_routes.py \\
      --network ../data/raw_data/81/81.net.xml \\
      --routes ../data/raw_data/81/81.rou.xml \\
      --output output/flow_test_data
  
  # 只提取数据，不生成热力图
  python extract_flow_from_routes.py \\
      --network ../data/raw_data/81/81.net.xml \\
      --routes ../data/raw_data/81/81.rou.xml \\
      --output output/flow_test_data \\
      --no-visualize
  
  # 只生成第0小时的热力图
  python extract_flow_from_routes.py \\
      --network ../data/raw_data/81/81.net.xml \\
      --routes ../data/raw_data/81/81.rou.xml \\
      --output output/flow_test_data \\
      --hour 0
        """
    )
    
    parser.add_argument('-n', '--network', type=str, required=True,
                       help='SUMO网络文件 (.net.xml)')
    parser.add_argument('-r', '--routes', type=str, required=True,
                       help='SUMO路由文件 (.rou.xml)')
    parser.add_argument('-o', '--output', type=str, default='output/flow_data',
                       help='输出目录，默认: output/flow_data')
    parser.add_argument('--visualize', action='store_true',
                       help='生成流量热力图（默认开启）', default=True)
    parser.add_argument('--no-visualize', action='store_false', dest='visualize',
                       help='不生成流量热力图')
    parser.add_argument('--hour', type=int, default=None,
                       help='指定要可视化的小时（默认为所有小时）')
    
    args = parser.parse_args()
    
    # 检查文件是否存在
    if not os.path.exists(args.network):
        print(f"错误: 网络文件不存在: {args.network}")
        sys.exit(1)
    
    if not os.path.exists(args.routes):
        print(f"错误: 路由文件不存在: {args.routes}")
        sys.exit(1)
    
    # 执行提取
    extractor = FlowExtractor(args.network, args.routes)
    
    print("="*60)
    print("SUMO路由流量提取工具")
    print("="*60)
    
    # 1. 加载网络
    extractor.load_network()
    
    # 2. 提取流量
    extractor.extract_flows()
    
    # 3. 导出数据
    extractor.export_flows(args.output)
    
    # 4. 生成热力图（可选）
    if args.visualize:
        if args.hour is not None:
            # 可视化指定小时
            extractor.visualize_hourly_flow_heatmap(args.output, args.hour)
        else:
            # 可视化所有小时
            for hour in sorted(extractor.hourly_flow.keys()):
                extractor.visualize_hourly_flow_heatmap(args.output, hour)
    
    print("\n" + "="*60)
    print("✓ 完成！")
    print("="*60)


if __name__ == '__main__':
    main()

