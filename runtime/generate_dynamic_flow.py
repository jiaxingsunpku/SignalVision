#!/usr/bin/env python3
"""
从OD文件生成SUMO的.rou.xml车流文件（使用dynamic/weibull模式）
模拟 vehiclegen.py 中的 gen_dynamic_weibull 逻辑
"""

import json
import argparse
import random
import numpy as np


def generate_dynamic_flow(od_file, output_file, 
                         scale=1.0, 
                         sim_duration=3600,
                         vehicle_type="DEFAULT_VEHTYPE",
                         mode='train',
                         seed=None):
    """
    生成动态车流（模拟 gen_dynamic_weibull）
    
    参数:
        od_file: OD JSON文件路径
        output_file: 输出的.rou.xml文件路径
        scale: 车流缩放因子
        sim_duration: 仿真时长（秒）
        vehicle_type: 车辆类型ID
        mode: 'train' 或 'test'，控制是否随机偏移
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
    
    if len(od_pairs) == 0:
        print("❌ 错误: 没有找到有效的OD对")
        return
    
    # ========== 第二步：生成Weibull分布的车流时间序列 ==========
    print(f"\n🚗 生成车流调度（Weibull分布）")
    print(f"   模式: {mode}")
    print(f"   缩放因子: {scale}")
    print(f"   仿真时长: {sim_duration}秒")
    
    # Weibull参数（与vehiclegen.py保持一致）
    _a = 2
    _lambda = 0.3 * sim_duration
    t = np.linspace(0, sim_duration, int(sim_duration))
    weibull_pdf = (_a/_lambda) * (t/_lambda)**(_a-1) * np.exp(-(t/_lambda)**_a)
    
    # 生成基础车流密度
    base_demand = weibull_pdf * 1e4 * scale + 1.0
    base_demand = np.clip(base_demand, 1.0, 8.0)
    base_demand[::2] = 0  # 偶数秒不生成车辆
    
    v_schedule = base_demand.astype(int)
    
    # 训练模式下进行随机偏移（数据增强）
    if mode != 'test':
        shift = np.random.randint(-int(sim_duration*0.1), int(sim_duration*0.1))
        v_schedule = np.roll(v_schedule, shift)
        print(f"   随机偏移: {shift}步")
    
    print(f"   非零时间步数: {np.count_nonzero(v_schedule)}")
    print(f"   预计总车辆数: {np.sum(v_schedule)}")
    
    # ========== 第三步：为每个时间步分配具体的OD对 ==========
    print(f"\n📝 为每个时间步分配OD对...")
    
    vehicle_schedule = []
    vehicle_id = 0
    
    for t in range(sim_duration):
        num_vehicles = v_schedule[t]
        if num_vehicles == 0:
            continue
        
        # 根据权重随机选择OD对
        for _ in range(num_vehicles):
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
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ')
        f.write('xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">\n')
        
        f.write(f'    <vType id="{vehicle_type}" accel="2.6" decel="4.5" sigma="0.5" ')
        f.write('length="5.0" minGap="2.5" maxSpeed="33.33" guiShape="passenger"/>\n')
        
        for veh_info in vehicle_schedule:
            f.write(f'    <vehicle id="{veh_info["vehicle_id"]}" type="{vehicle_type}" ')
            f.write(f'depart="{veh_info["depart_time"]:.1f}" departLane="best" departSpeed="max">\n')
            f.write(f'        <route edges="{veh_info["route"]}"/>\n')
            f.write(f'    </vehicle>\n')
        
        f.write('</routes>\n')
    
    # ========== 统计信息 ==========
    max_depart = max(v['depart_time'] for v in vehicle_schedule) if vehicle_schedule else 0
    
    # 分时段统计（验证Weibull分布）
    time_bins = [0, 600, 1200, 1800, 2400, 3000, 3600]
    print(f"\n📊 时间段车辆分布（验证Weibull形状）：")
    for i in range(len(time_bins)-1):
        start, end = time_bins[i], time_bins[i+1]
        count = sum(1 for v in vehicle_schedule if start <= v['depart_time'] < end)
        print(f"  {start}-{end}秒 ({start//60}-{end//60}分钟): {count}辆车")
    
    print(f"\n=== 车流生成统计 ===")
    print(f"模式: dynamic (Weibull分布)")
    print(f"缩放因子: {scale}")
    print(f"仿真时长: {sim_duration}秒 ({sim_duration/60:.1f}分钟)")
    print(f"实际生成车辆: {total_vehicles} 辆")
    print(f"车流时间范围: 0.0 - {max_depart:.1f} 秒")
    print(f"平均车辆密度: {total_vehicles/sim_duration*60:.2f} 辆/分钟")
    print(f"输出文件: {output_file}")
    print("✅ 转换完成！")


def main():
    parser = argparse.ArgumentParser(
        description='从OD文件生成SUMO的.rou.xml车流文件（dynamic/Weibull模式）'
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
        default=1.0,
        help='车流缩放因子（默认: 1.0），建议范围0.5-3.0'
    )
    parser.add_argument(
        '--sim-duration',
        type=int,
        default=3600,
        help='仿真时长（秒），默认3600秒（1小时）'
    )
    parser.add_argument(
        '--mode',
        type=str,
        default='train',
        choices=['train', 'test'],
        help='模式：train会随机偏移，test不偏移（默认: train）'
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
    
    generate_dynamic_flow(
        args.input,
        args.output,
        args.scale,
        args.sim_duration,
        args.vehicle_type,
        args.mode,
        args.seed
    )


if __name__ == '__main__':
    main()

