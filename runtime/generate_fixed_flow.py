#!/usr/bin/env python3
"""
从OD文件生成SUMO的.rou.xml车流文件（使用fixed density模式）
模拟 vehiclegen.py 中的 gen_dynamic_wrt_density 逻辑
"""

import json
import argparse
import random
import numpy as np


def generate_fixed_density_flow(od_file, output_file, 
                                 scale=1.0, 
                                 sim_duration=3600,
                                 vehicle_type="DEFAULT_VEHTYPE",
                                 seed=None):
    """
    生成固定密度的车流（模拟 gen_dynamic_wrt_density）
    
    参数:
        od_file: OD JSON文件路径
        output_file: 输出的.rou.xml文件路径
        scale: 车流缩放因子（对应vehiclegen中的self.scale）
        sim_duration: 仿真时长（秒）
        vehicle_type: 车辆类型ID
        seed: 随机种子（可选）
    """
    
    if seed is not None:
        np.random.seed(seed)
        random.seed(seed)
    else:
        np.random.seed()
    
    print(f"📖 正在读取OD文件: {od_file}")
    with open(od_file, 'r', encoding='utf-8') as f:
        od_data = json.load(f)
    
    # ========== 第一步：收集所有有效的OD对 ==========
    od_pairs = []
    total_weight = 0
    
    for origin, destinations in od_data.items():
        for dest_info in destinations:
            destination = dest_info['destination']
            route_edges = dest_info['route']
            weight = dest_info['weight']
            
            # 只保留有权重且有路径的OD对
            if weight > 0 and route_edges and len(route_edges) > 0:
                edges_str = ' '.join(str(edge) for edge in route_edges)
                if edges_str.strip():
                    od_pairs.append({
                        'origin': origin,
                        'destination': destination,
                        'route': edges_str,
                        'weight': weight
                    })
                    total_weight += weight
    
    print(f"📊 有效OD对数量: {len(od_pairs)}")
    print(f"📊 总权重: {total_weight}")
    
    if len(od_pairs) == 0:
        print("❌ 错误: 没有找到有效的OD对")
        return
    
    # 计算每个OD对的概率（基于权重）
    od_probabilities = [od['weight'] / total_weight for od in od_pairs]
    
    # ========== 第二步：生成车辆时间调度（fixed density模式）==========
    # 这里复制 gen_dynamic_wrt_density 的逻辑
    print(f"\n🚗 生成车流调度（fixed density模式）")
    print(f"   缩放因子: {scale}")
    print(f"   仿真时长: {sim_duration}秒")
    
    # 使用固定密度，每2秒生成一批车辆
    v_schedule = np.array([np.clip(scale, 1.0, 12.0) for _ in range(sim_duration)]).astype(int)
    v_schedule[::2] = 0  # 偶数秒不生成车辆
    
    print(f"   非零时间步数: {np.count_nonzero(v_schedule)}")
    print(f"   预计总车辆数: {np.sum(v_schedule)}")
    
    # ========== 第三步：为每个时间步分配具体的OD对 ==========
    print(f"\n📝 为每个时间步分配OD对...")
    
    vehicle_schedule = []  # 存储每辆车的信息
    vehicle_id = 0
    
    for t in range(sim_duration):
        num_vehicles = v_schedule[t]
        if num_vehicles == 0:
            continue
        
        # 根据权重随机选择OD对
        for _ in range(num_vehicles):
            # 使用Dirichlet分布增加随机性（模拟vehiclegen的逻辑）
            probs = np.random.dirichlet(np.ones(len(od_pairs)))
            chosen_idx = np.random.choice(len(od_pairs), p=probs)
            chosen_od = od_pairs[chosen_idx]
            
            vehicle_schedule.append({
                'depart_time': float(t),
                'route': chosen_od['route'],
                'vehicle_id': vehicle_id,
                'od_name': f"{chosen_od['origin']}->{chosen_od['destination']}"
            })
            vehicle_id += 1
    
    total_vehicles = len(vehicle_schedule)
    print(f"✅ 成功生成 {total_vehicles} 辆车的调度")
    
    # ========== 第四步：写入XML文件 ==========
    print(f"\n💾 写入XML文件: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # 写入XML头部
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ')
        f.write('xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">\n')
        
        # 添加车辆类型定义
        f.write(f'    <vType id="{vehicle_type}" accel="2.6" decel="4.5" sigma="0.5" ')
        f.write('length="5.0" minGap="2.5" maxSpeed="33.33" guiShape="passenger"/>\n')
        
        # 写入所有车辆
        for veh_info in vehicle_schedule:
            f.write(f'    <vehicle id="{veh_info["vehicle_id"]}" type="{vehicle_type}" ')
            f.write(f'depart="{veh_info["depart_time"]:.1f}" departLane="best" departSpeed="max">\n')
            f.write(f'        <route edges="{veh_info["route"]}"/>\n')
            f.write(f'    </vehicle>\n')
        
        # 写入结束标签
        f.write('</routes>\n')
    
    # ========== 第五步：统计信息 ==========
    max_depart = max(v['depart_time'] for v in vehicle_schedule) if vehicle_schedule else 0
    
    print(f"\n=== 车流生成统计 ===")
    print(f"模式: fixed density")
    print(f"缩放因子: {scale}")
    print(f"仿真时长: {sim_duration}秒 ({sim_duration/60:.1f}分钟)")
    print(f"实际生成车辆: {total_vehicles} 辆")
    print(f"车流时间范围: 0.0 - {max_depart:.1f} 秒")
    print(f"平均车辆密度: {total_vehicles/sim_duration*60:.2f} 辆/分钟")
    print(f"输出文件: {output_file}")
    print("✅ 转换完成！")
    
    # 打印前10辆车的信息
    print(f"\n📋 前10辆车的出发时间：")
    for i, veh in enumerate(vehicle_schedule[:10]):
        print(f"  车辆{veh['vehicle_id']}: t={veh['depart_time']:.1f}秒, OD={veh['od_name'][:50]}")


def main():
    parser = argparse.ArgumentParser(
        description='从OD文件生成SUMO的.rou.xml车流文件（fixed density模式）'
    )
    parser.add_argument(
        '--input',
        default='data/raw_data/81/od.json',
        help='输入的OD JSON文件路径'
    )
    parser.add_argument(
        '--output',
        default='/home/sjx/jx/project/sumo-ppo-gnn/cache/81/81.rou.xml',
        help='输出的.rou.xml文件路径'
    )
    parser.add_argument(
        '--scale',
        type=float,
        default=4.0,
        help='车流缩放因子（默认: 2.0），建议范围1.0-12.0'
    )
    parser.add_argument(
        '--sim-duration',
        type=int,
        default=2400,
        help='仿真时长（秒），默认3600秒（1小时）'
    )
    parser.add_argument(
        '--vehicle-type',
        type=str,
        default='DEFAULT_VEHTYPE',
        help='车辆类型ID（默认: DEFAULT_VEHTYPE）'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='随机种子（可选），用于可重复的结果'
    )
    
    args = parser.parse_args()
    
    generate_fixed_density_flow(
        args.input,
        args.output,
        args.scale,
        args.sim_duration,
        args.vehicle_type,
        args.seed
    )


if __name__ == '__main__':
    main()

