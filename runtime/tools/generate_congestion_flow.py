#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_congestion_flow.py  —  局部拥堵场景生成器

功能：
  1. 从路网中选取信号灯路口作为拥堵中心（可自动或手动指定）
  2. BFS 找到 k 跳内所有邻居路口及其连接边（拥堵区域）
  3. 截取原始路由文件的前 time_limit 秒
  4. 对在激增时段 [surge_start, surge_end) 内、且经过拥堵区域的车辆放大 amplify 倍
  5. 按出发时间重排序后输出新路由文件

用法:
    python generate_congestion_flow.py \\
        --net  data/raw_data/ezhou/ezhou.net.xml \\
        --routes data/raw_data/ezhou/ezhou.rou.xml \\
        --output data/raw_data/ezhou/ezhou_congested.rou.xml

    # 指定中心路口，只在 1200~2400s 之间激增
    python generate_congestion_flow.py \\
        --net  data/raw_data/ezhou/ezhou.net.xml \\
        --routes data/raw_data/ezhou/ezhou.rou.xml \\
        --output data/raw_data/ezhou/ezhou_congested.rou.xml \\
        --center J020 --hops 3 --amplify 5 \\
        --surge_start 1200 --surge_end 2400
"""

import os
import sys
import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict, deque

# ── SUMO 工具路径 ────────────────────────────────────────────────────────────
if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
    import sumolib
else:
    sys.exit("错误: 请设置 SUMO_HOME 环境变量")


# ════════════════════════════════════════════════════════════════════════════
#  路网分析
# ════════════════════════════════════════════════════════════════════════════

def bfs_k_hops(center: str, adj: dict, k: int) -> set:
    """从 center 出发，BFS 返回 k 跳以内所有节点（包含 center）"""
    visited = {center}
    frontier = [center]
    for _ in range(k):
        next_f = []
        for node in frontier:
            for nbr in adj.get(node, []):
                if nbr not in visited:
                    visited.add(nbr)
                    next_f.append(nbr)
        frontier = next_f
    return visited


def build_congestion_zone(net_file: str, center_junc: str | None, hops: int):
    """
    解析路网，返回：
        center_junc  : 拥堵中心路口 ID
        zone_juncs   : 拥堵区域路口集合
        zone_edges   : 拥堵区域边集合（两端均在区域内的边）
    """
    print(f"[1/3] 加载路网: {net_file}")
    net = sumolib.net.readNet(net_file)

    tls_ids = {tls.getID() for tls in net.getTrafficLights()}
    print(f"      信号灯路口: {len(tls_ids)} 个")

    # 构建路口无向邻接表 & 边映射
    adj = defaultdict(set)
    edge_map: dict[str, tuple[str, str]] = {}   # edge_id -> (from_junc, to_junc)

    for edge in net.getEdges():
        if edge.isSpecial() or edge.getFunction() == 'internal':
            continue
        f = edge.getFromNode().getID()
        t = edge.getToNode().getID()
        adj[f].add(t)
        adj[t].add(f)
        edge_map[edge.getID()] = (f, t)

    all_junc_ids = {node.getID() for node in net.getNodes()}

    # ── 自动选择中心路口 ──
    if center_junc is None:
        print("      自动选取中心路口（最大 TLS 邻居数）...")
        best, best_score = None, -1
        for jid in tls_ids:
            zone = bfs_k_hops(jid, adj, hops)
            # 评分 = k跳内TLS路口数 × 总路口数（兼顾密度和规模）
            score = sum(1 for j in zone if j in tls_ids) * len(zone)
            if score > best_score:
                best_score, best = score, jid
        center_junc = best
    else:
        if center_junc not in all_junc_ids:
            sys.exit(f"错误: 路口 '{center_junc}' 不在路网中\n"
                     f"  信号灯路口示例: {sorted(tls_ids)[:10]}")

    # ── 找 k 跳邻居 ──
    zone_juncs = bfs_k_hops(center_junc, adj, hops)
    tls_in_zone = sum(1 for j in zone_juncs if j in tls_ids)
    print(f"      拥堵中心路口 : {center_junc}")
    print(f"      {hops} 跳范围路口 : {len(zone_juncs)} 个（含 {tls_in_zone} 个信号灯路口）")

    # ── 找区域内边（两端均在区域内）──
    zone_edges: set[str] = set()
    for eid, (f, t) in edge_map.items():
        if f in zone_juncs and t in zone_juncs:
            zone_edges.add(eid)
    print(f"      拥堵区域边数  : {len(zone_edges)} 条")

    return center_junc, zone_juncs, zone_edges


# ════════════════════════════════════════════════════════════════════════════
#  边 ID 匹配工具
# ════════════════════════════════════════════════════════════════════════════

def normalize_edge_id(eid: str) -> str:
    """
    处理 duarouter 产生的内部切割边 ID，例如：
        '457722337#2.1396'  →  '457722337#2'
        '-457722337#2.1396' →  '-457722337#2'
    """
    if '#' in eid:
        base, seg = eid.split('#', 1)
        seg_base = seg.split('.')[0]
        return f"{base}#{seg_base}"
    # 没有 # 的边（如 'E2', '-E5'）
    dot_pos = eid.rfind('.')
    if dot_pos > 0 and eid[dot_pos - 1].isdigit():
        return eid[:dot_pos]
    return eid


def route_uses_zone(edges_str: str, zone_edges: set, norm_zone: set) -> bool:
    """判断路由是否经过拥堵区域"""
    for eid in edges_str.split():
        if eid in zone_edges:
            return True
        if normalize_edge_id(eid) in norm_zone:
            return True
    return False


# ════════════════════════════════════════════════════════════════════════════
#  路由文件处理
# ════════════════════════════════════════════════════════════════════════════

def process_route_file(
    route_file: str,
    output_file: str,
    zone_edges: set,
    time_limit: float,
    amplify: int,
    surge_start: float,
    surge_end: float,
) -> dict:
    """
    流式读取路由文件，收集 [0, time_limit) 内车辆，
    对拥堵区域内的车辆在激增时段复制 amplify 份，
    排序后写出。
    返回统计信息字典。
    """
    # 归一化边集合，用于子边匹配
    norm_zone = {normalize_edge_id(e) for e in zone_edges}

    # ── 收集数据 ──
    vehicles: list[tuple] = []   # (depart, vid, vtype, dep_str, from_taz, to_taz, edges)
    vtype_attribs: dict | None = None
    n_total = n_skipped = n_amplified = 0

    print(f"[2/3] 读取路由文件: {route_file}")
    print(f"      时间窗口  : 0 ~ {time_limit}s")
    print(f"      激增时段  : {surge_start}s ~ {surge_end}s，×{amplify}")

    # iterparse：在 'end' 事件拿到完整元素
    # 注意：不能在 vehicle 的 end 事件前清理其子元素（如 route），
    # 否则 elem.find('route') 将获得空元素。
    context = ET.iterparse(route_file, events=('start', 'end'))
    root_elem = None

    for event, elem in context:
        # 跳过注释/PI（tag 是 callable）
        if callable(elem.tag):
            continue

        if event == 'start' and elem.tag == 'routes':
            root_elem = elem
            continue

        if event != 'end':
            continue

        tag = elem.tag

        if tag == 'vType':
            vtype_attribs = dict(elem.attrib)
            # 从 root 移除以释放内存
            if root_elem is not None:
                try:
                    root_elem.remove(elem)
                except ValueError:
                    pass
            elem.clear()
            continue

        # 只处理 routes 的直接子元素 vehicle；
        # 其他 tag（route、stop 等子元素）跳过——不能清理，等父 vehicle 处理完后一起清理
        if tag != 'vehicle':
            continue

        # ── 处理 vehicle ──
        n_total += 1
        depart = float(elem.get('depart', '0'))

        if depart >= time_limit:
            n_skipped += 1
            if root_elem is not None:
                root_elem.remove(elem)
            elem.clear()
            continue

        vid       = elem.get('id', str(n_total))
        vtype     = elem.get('type', 'DEFAULT_VEHTYPE')
        dep_str   = elem.get('depart', f'{depart:.2f}')
        from_taz  = elem.get('fromTaz', '')
        to_taz    = elem.get('toTaz', '')
        route_el  = elem.find('route')
        edges_str = route_el.get('edges', '') if route_el is not None else ''

        # 原始车辆
        vehicles.append((depart, vid, vtype, dep_str, from_taz, to_taz, edges_str))

        # 判断是否在激增时段且经过拥堵区域
        in_surge = surge_start <= depart < surge_end
        if in_surge and edges_str and route_uses_zone(edges_str, zone_edges, norm_zone):
            for i in range(1, amplify):
                new_dep = depart + i * 0.01          # 微小偏移保持排序稳定
                vehicles.append((
                    new_dep,
                    f"{vid}_dup{i}",
                    vtype,
                    f"{new_dep:.2f}",
                    from_taz,
                    to_taz,
                    edges_str,
                ))
            n_amplified += 1

        if root_elem is not None:
            try:
                root_elem.remove(elem)
            except ValueError:
                pass
        elem.clear()

        if n_total % 50_000 == 0:
            print(f"      已读取 {n_total:,} 辆 / 已收集 {len(vehicles):,} 辆...")

    # ── 排序 ──
    print(f"      读取完毕，共 {n_total:,} 辆，保留 {len(vehicles):,} 辆，排序中...")
    vehicles.sort(key=lambda x: x[0])

    # ── 写出 ──
    print(f"      写入: {output_file}")
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write(
            '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">\n'
        )

        # vType
        if vtype_attribs:
            attrs_str = ' '.join(f'{k}="{v}"' for k, v in vtype_attribs.items())
            out.write(f'    <vType {attrs_str}/>\n')

        # 车辆
        for (dep_f, vid, vtype, dep_str, from_taz, to_taz, edges) in vehicles:
            parts = [f'id="{vid}"', f'type="{vtype}"', f'depart="{dep_str}"']
            if from_taz:
                parts.append(f'fromTaz="{from_taz}"')
            if to_taz:
                parts.append(f'toTaz="{to_taz}"')
            out.write(f'    <vehicle {" ".join(parts)}>\n')
            out.write(f'        <route edges="{edges}"/>\n')
            out.write(f'    </vehicle>\n')

        out.write('</routes>\n')

    n_copies  = len(vehicles) - (n_total - n_skipped)
    n_output  = len(vehicles)

    return {
        'n_total':      n_total,
        'n_skipped':    n_skipped,
        'n_kept':       n_total - n_skipped,
        'n_amplified':  n_amplified,
        'n_copies':     n_copies,
        'n_output':     n_output,
    }


# ════════════════════════════════════════════════════════════════════════════
#  区域信息输出
# ════════════════════════════════════════════════════════════════════════════

def save_zone_info(info_file: str, center: str, hops: int,
                   zone_juncs: set, zone_edges: set):
    with open(info_file, 'w', encoding='utf-8') as f:
        f.write(f"拥堵中心路口 : {center}\n")
        f.write(f"邻居跳数     : {hops}\n")
        f.write(f"区域路口数   : {len(zone_juncs)}\n")
        f.write(f"区域边数     : {len(zone_edges)}\n")
        f.write("\n── 路口列表 ──────────────────────────\n")
        for j in sorted(zone_juncs):
            f.write(f"  {j}\n")
        f.write("\n── 边列表 ────────────────────────────\n")
        for e in sorted(zone_edges):
            f.write(f"  {e}\n")
    print(f"      区域信息 → {info_file}")


# ════════════════════════════════════════════════════════════════════════════
#  主函数
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='局部拥堵场景 SUMO 路由文件生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('-n', '--net', required=True,
                        help='SUMO 路网文件 (.net.xml)')
    parser.add_argument('-r', '--routes', required=True,
                        help='原始 SUMO 路由文件 (.rou.xml)')
    parser.add_argument('-o', '--output', required=True,
                        help='输出路由文件路径 (.rou.xml)')
    parser.add_argument('--center', default=None,
                        help='拥堵中心路口 ID（默认: 自动选取连接最密集的信号灯路口）')
    parser.add_argument('--hops', type=int, default=3,
                        help='邻居路口跳数 (默认: 3)')
    parser.add_argument('--time_limit', type=float, default=3600.0,
                        help='截取的仿真时长（秒），超出部分丢弃 (默认: 3600)')
    parser.add_argument('--amplify', type=int, default=3,
                        help='拥堵区域车流放大倍数 (默认: 3，即原始+2份副本)')
    parser.add_argument('--surge_start', type=float, default=0.0,
                        help='车流激增起始时间（秒）(默认: 0，从头开始)')
    parser.add_argument('--surge_end', type=float, default=3600.0,
                        help='车流激增结束时间（秒）(默认: 3600，整段激增)')
    args = parser.parse_args()

    # 文件检查
    for f in [args.net, args.routes]:
        if not os.path.exists(f):
            sys.exit(f"错误: 文件不存在: {f}")

    print("=" * 60)
    print("  局部拥堵场景生成器")
    print("=" * 60)

    # ── 步骤1: 构建拥堵区域 ──
    center, zone_juncs, zone_edges = build_congestion_zone(
        args.net, args.center, args.hops)

    # 保存区域信息
    info_file = args.output.replace('.rou.xml', '_zone_info.txt')
    if not args.output.endswith('.rou.xml'):
        info_file = args.output + '_zone_info.txt'
    save_zone_info(info_file, center, args.hops, zone_juncs, zone_edges)

    # ── 步骤2: 处理路由文件 ──
    stats = process_route_file(
        route_file  = args.routes,
        output_file = args.output,
        zone_edges  = zone_edges,
        time_limit  = args.time_limit,
        amplify     = args.amplify,
        surge_start = args.surge_start,
        surge_end   = args.surge_end,
    )

    # ── 步骤3: 统计报告 ──
    print()
    print(f"[3/3] 完成！")
    print("=" * 60)
    print(f"  输出文件   : {args.output}")
    print(f"  拥堵中心   : {center}  ({args.hops}跳)")
    print(f"  区域路口数 : {len(zone_juncs)}")
    print(f"  区域边数   : {len(zone_edges)}")
    print(f"  激增时段   : {args.surge_start}s ~ {args.surge_end}s  (×{args.amplify})")
    print("─" * 60)
    print(f"  原始总车辆 : {stats['n_total']:>8,}")
    print(f"  超时丢弃   : {stats['n_skipped']:>8,}  (depart ≥ {args.time_limit}s)")
    print(f"  时段内车辆 : {stats['n_kept']:>8,}")
    print(f"  被放大车辆 : {stats['n_amplified']:>8,}  (经过拥堵区域且在激增时段)")
    print(f"  新增副本   : {stats['n_copies']:>8,}  (×{args.amplify - 1})")
    print(f"  输出总车辆 : {stats['n_output']:>8,}")
    amplify_ratio = stats['n_copies'] / max(stats['n_kept'], 1) * 100
    print(f"  拥堵放大率 : {amplify_ratio:>7.1f}%  (副本 / 时段内车辆)")
    print("=" * 60)


if __name__ == '__main__':
    main()
