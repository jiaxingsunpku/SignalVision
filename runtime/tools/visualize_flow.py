#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
visualize_flow.py  —  路网流量热力图可视化（支持对比 & 区域放大）

用法:
    # 单图
    conda run -n traffic python tools/visualize_flow.py \\
        --net  data/raw_data/ezhou/ezhou.net.xml \\
        --routes data/raw_data/ezhou/ezhou.rou.xml \\
        --time_limit 3600 --output tools/output/ezhou_orig.png

    # 对比图（自动生成差值图 + 区域放大）
    conda run -n traffic python tools/visualize_flow.py \\
        --net  data/raw_data/ezhou/ezhou.net.xml \\
        --routes data/raw_data/ezhou/ezhou.rou.xml \\
                 data/raw_data/ezhou/ezhou_congested_3x.rou.xml \\
        --titles "Original (0-3600s)" "Congested ×3 (0-3600s)" \\
        --zone   data/raw_data/ezhou/ezhou_congested_3x_zone_info.txt \\
        --time_limit 3600 \\
        --output tools/output/ezhou_compare.png
"""

import os
import sys
import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
from matplotlib.collections import LineCollection
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch

# ── 中文字体注册 ────────────────────────────────────────────────────────────
_CN_FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
if os.path.exists(_CN_FONT):
    font_manager.fontManager.addfont(_CN_FONT)
    plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
    import sumolib
else:
    sys.exit("错误: 请设置 SUMO_HOME 环境变量")

BG = '#0d1117'


# ════════════════════════════════════════════════════════════════════════════
#  路网加载
# ════════════════════════════════════════════════════════════════════════════

def load_network(net_file: str):
    print(f"[1] 加载路网: {net_file}")
    net = sumolib.net.readNet(net_file)
    edge_shapes: dict[str, list] = {}
    for edge in net.getEdges():
        if edge.isSpecial() or edge.getFunction() == 'internal':
            continue
        shape = edge.getShape()
        if len(shape) >= 2:
            edge_shapes[edge.getID()] = list(shape)
    node_pos: dict[str, tuple] = {
        n.getID(): n.getCoord()[:2] for n in net.getNodes()
    }
    all_x = [p[0] for s in edge_shapes.values() for p in s]
    all_y = [p[1] for s in edge_shapes.values() for p in s]
    bbox = (min(all_x), min(all_y), max(all_x), max(all_y))
    print(f"   边: {len(edge_shapes)},  节点: {len(node_pos)}")
    return edge_shapes, node_pos, bbox


# ════════════════════════════════════════════════════════════════════════════
#  流量统计
# ════════════════════════════════════════════════════════════════════════════

def _base_edge(eid: str) -> str:
    if '#' in eid:
        b, s = eid.split('#', 1)
        return f"{b}#{s.split('.')[0]}"
    dot = eid.rfind('.')
    if dot > 0 and eid[dot - 1].isdigit():
        return eid[:dot]
    return eid


def count_flows(route_file: str, time_limit: float = None) -> dict[str, int]:
    flow: dict[str, int] = defaultdict(int)
    n = 0
    context = ET.iterparse(route_file, events=('start', 'end'))
    root = None
    for event, elem in context:
        if callable(elem.tag):
            continue
        if event == 'start' and elem.tag == 'routes':
            root = elem; continue
        if event != 'end' or elem.tag != 'vehicle':
            continue
        depart = float(elem.get('depart', '0'))
        if time_limit is not None and depart >= time_limit:
            if root is not None:
                try: root.remove(elem)
                except ValueError: pass
            elem.clear(); continue
        route_el = elem.find('route')
        if route_el is not None:
            for eid in route_el.get('edges', '').split():
                flow[eid] += 1
                base = _base_edge(eid)
                if base != eid:
                    flow[base] += 1
            n += 1
        if root is not None:
            try: root.remove(elem)
            except ValueError: pass
        elem.clear()
        if n % 50_000 == 0 and n > 0:
            print(f"   已读 {n:,} 辆...")
    print(f"   统计完: {n:,} 辆, {len(flow):,} 条边")
    return dict(flow)


# ════════════════════════════════════════════════════════════════════════════
#  区域信息
# ════════════════════════════════════════════════════════════════════════════

def load_zone(zone_file: str):
    center, juncs, edges = '', set(), set()
    mode = None
    with open(zone_file, encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if '拥堵中心路口' in s: center = s.split(':', 1)[1].strip()
            elif '路口列表' in s:   mode = 'j'
            elif '边列表' in s:     mode = 'e'
            elif s and mode == 'j': juncs.add(s)
            elif s and mode == 'e': edges.add(s)
    return center, juncs, edges


def zone_bbox(juncs: set, node_pos: dict, pad_ratio: float = 0.35):
    """根据区域路口坐标计算裁剪框（带 padding）"""
    xs = [node_pos[j][0] for j in juncs if j in node_pos]
    ys = [node_pos[j][1] for j in juncs if j in node_pos]
    if not xs:
        return None
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    px, py = w * pad_ratio, h * pad_ratio
    return (min(xs) - px, min(ys) - py, max(xs) + px, max(ys) + py)


# ════════════════════════════════════════════════════════════════════════════
#  核心绘图函数
# ════════════════════════════════════════════════════════════════════════════

def _segs(shape):
    return [[shape[i], shape[i + 1]] for i in range(len(shape) - 1)]


def draw_flow(ax, edge_shapes, flow, norm, cmap, bbox,
              title='', subtitle='',
              zone_edges=None, zone_juncs=None,
              node_pos=None, zone_center='',
              highlight_zone=True):
    """通用流量绘制，norm/cmap 由外部统一传入（保证多图色阶一致）"""
    ax.set_facecolor(BG)

    # 底图（无流量，暗灰）
    zero_segs = [s for eid, shape in edge_shapes.items()
                 if flow.get(eid, 0) == 0 for s in _segs(shape)]
    if zero_segs:
        ax.add_collection(LineCollection(zero_segs, linewidths=0.2,
                                         colors='#1d2035', alpha=0.7, zorder=1))

    # 有流量边（按共享色阶着色）
    flow_segs, fvals = [], []
    vmax_for_lw = norm.vmax if hasattr(norm, 'vmax') else 1
    for eid, shape in edge_shapes.items():
        f = flow.get(eid, 0)
        if f > 0:
            for seg in _segs(shape):
                flow_segs.append(seg)
                fvals.append(f)
    if flow_segs:
        colors = [cmap(norm(v)) for v in fvals]
        # 线宽：流量越大线越粗，最细 0.5，最粗 3.5
        lw = [0.5 + (v / max(vmax_for_lw, 1)) ** 0.5 * 3.0 for v in fvals]
        ax.add_collection(LineCollection(flow_segs, linewidths=lw,
                                         colors=colors, alpha=0.95, zorder=2))

    # 拥堵区域橙色轮廓
    if highlight_zone and zone_edges:
        z_segs = [s for eid in zone_edges
                  if (shape := edge_shapes.get(eid)) for s in _segs(shape)]
        if z_segs:
            ax.add_collection(LineCollection(z_segs, linewidths=4,
                                             colors='#ff8800', alpha=0.18, zorder=3))
            ax.add_collection(LineCollection(z_segs, linewidths=1.2,
                                             colors='#ffcc44', alpha=0.65, zorder=4))

    # 路口圆点
    if highlight_zone and zone_juncs and node_pos:
        xs = [node_pos[j][0] for j in zone_juncs if j in node_pos]
        ys = [node_pos[j][1] for j in zone_juncs if j in node_pos]
        if xs:
            ax.scatter(xs, ys, s=5, c='#ffcc44', alpha=0.55,
                       zorder=5, linewidths=0)

    # 中心路口星号
    if zone_center and node_pos and zone_center in node_pos:
        cx, cy = node_pos[zone_center]
        ax.plot(cx, cy, '*', color='#ffffff', markersize=10,
                markeredgecolor='#ffcc44', markeredgewidth=0.8, zorder=6)
        ax.annotate(f' {zone_center}', (cx, cy), color='#ffdd88',
                    fontsize=7.5, zorder=7,
                    xytext=(4, 4), textcoords='offset points')

    xmin, ymin, xmax, ymax = bbox
    mx = (xmax - xmin) * 0.02
    my = (ymax - ymin) * 0.02
    ax.set_xlim(xmin - mx, xmax + mx)
    ax.set_ylim(ymin - my, ymax + my)
    ax.set_aspect('equal')
    ax.axis('off')

    if title:
        ax.set_title(title, color='white', fontsize=11,
                     fontweight='bold', pad=5)
    if subtitle:
        ax.text(0.5, 1.0, subtitle, transform=ax.transAxes,
                color='#aaaaaa', fontsize=8, ha='center', va='bottom')

    # 右下角英文统计
    n_active = sum(1 for e in edge_shapes if flow.get(e, 0) > 0)
    peak = max(flow.get(e, 0) for e in edge_shapes) if flow else 0
    ax.text(0.99, 0.01,
            f"active: {n_active}/{len(edge_shapes)}  peak: {peak:,}",
            transform=ax.transAxes, color='#666666',
            fontsize=6.5, va='bottom', ha='right',
            fontfamily='DejaVu Sans')


def draw_diff(ax, edge_shapes, flow_a, flow_b, bbox, title='',
              zone_edges=None, zone_juncs=None,
              node_pos=None, zone_center=''):
    """差值图 B−A，红=增加，蓝=减少，白/灰=不变"""
    ax.set_facecolor(BG)

    diff = {eid: flow_b.get(eid, 0) - flow_a.get(eid, 0)
            for eid in set(flow_a) | set(flow_b)}
    diff = {k: v for k, v in diff.items() if v != 0}

    # 底图
    zero_segs = [s for eid, shape in edge_shapes.items()
                 if diff.get(eid, 0) == 0 for s in _segs(shape)]
    if zero_segs:
        ax.add_collection(LineCollection(zero_segs, linewidths=0.2,
                                         colors='#1d2035', alpha=0.7, zorder=1))

    if diff:
        max_abs = max(abs(v) for v in diff.values())
        norm = mcolors.TwoSlopeNorm(vmin=-max_abs, vcenter=0, vmax=max_abs)
        cmap = matplotlib.colormaps.get_cmap('RdBu_r')

        d_segs, dvals = [], []
        for eid, shape in edge_shapes.items():
            d = diff.get(eid, 0)
            if d != 0:
                for seg in _segs(shape):
                    d_segs.append(seg)
                    dvals.append(d)
        if d_segs:
            colors = [cmap(norm(v)) for v in dvals]
            lw = [0.5 + abs(v) / max_abs * 3.0 for v in dvals]
            ax.add_collection(LineCollection(d_segs, linewidths=lw,
                                             colors=colors, alpha=0.95, zorder=2))

        # 区域轮廓
        if zone_edges:
            z_segs = [s for eid in zone_edges
                      if (shape := edge_shapes.get(eid)) for s in _segs(shape)]
            if z_segs:
                ax.add_collection(LineCollection(z_segs, linewidths=4,
                                                 colors='#ff8800', alpha=0.18, zorder=3))
                ax.add_collection(LineCollection(z_segs, linewidths=1.0,
                                                 colors='#ffcc44', alpha=0.55, zorder=4))
        if zone_juncs and node_pos:
            xs = [node_pos[j][0] for j in zone_juncs if j in node_pos]
            ys = [node_pos[j][1] for j in zone_juncs if j in node_pos]
            if xs:
                ax.scatter(xs, ys, s=5, c='#ffcc44', alpha=0.45,
                           zorder=5, linewidths=0)
        if zone_center and node_pos and zone_center in node_pos:
            cx, cy = node_pos[zone_center]
            ax.plot(cx, cy, '*', color='#ffffff', markersize=10,
                    markeredgecolor='#ffcc44', markeredgewidth=0.8, zorder=6)

        # colorbar
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.01)
        cbar.set_label('ΔVehicles (B−A)', color='#cccccc', fontsize=7.5)
        cbar.ax.tick_params(colors='#aaaaaa', labelsize=6)
        plt.setp(plt.getp(cbar.ax, 'yticklabels'), color='#aaaaaa')
        cbar.outline.set_edgecolor('#444444')

        n_inc = sum(1 for v in diff.values() if v > 0)
        ax.text(0.99, 0.01,
                f"+edges: {n_inc}  peak delta: +{int(max_abs):,}",
                transform=ax.transAxes, color='#666666',
                fontsize=6.5, va='bottom', ha='right',
                fontfamily='DejaVu Sans')

    xmin, ymin, xmax, ymax = bbox
    mx = (xmax - xmin) * 0.02
    my = (ymax - ymin) * 0.02
    ax.set_xlim(xmin - mx, xmax + mx)
    ax.set_ylim(ymin - my, ymax + my)
    ax.set_aspect('equal')
    ax.axis('off')
    if title:
        ax.set_title(title, color='white', fontsize=11,
                     fontweight='bold', pad=5)


def add_shared_colorbar(fig, axes, norm, cmap, label='vehicles', log_scale=False):
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, fraction=0.015, pad=0.01)
    cbar.set_label(label, color='#cccccc', fontsize=8)
    cbar.ax.tick_params(colors='#aaaaaa', labelsize=7)
    plt.setp(plt.getp(cbar.ax, 'yticklabels'), color='#aaaaaa')
    cbar.outline.set_edgecolor('#444444')


# ════════════════════════════════════════════════════════════════════════════
#  主函数
# ════════════════════════════════════════════════════════════════════════════

def visualize(net_file, route_files, output_file,
              titles=None, time_limit=None, zone_file=None,
              log_scale=False, cmap_name='hot_r', figwidth=20.0):

    edge_shapes, node_pos, full_bbox = load_network(net_file)

    zone_center, zone_juncs, zone_edges = '', None, None
    zbbox = None
    if zone_file and os.path.exists(zone_file):
        zone_center, zone_juncs, zone_edges = load_zone(zone_file)
        zbbox = zone_bbox(zone_juncs, node_pos, pad_ratio=0.4)
        print(f"   区域: 中心={zone_center}, 路口={len(zone_juncs)}, 边={len(zone_edges)}")

    flows = []
    for i, rf in enumerate(route_files):
        print(f"[{i + 2}] 统计: {rf}")
        flows.append(count_flows(rf, time_limit=time_limit))

    n_route = len(route_files)
    has_zone = zbbox is not None
    compare  = n_route == 2

    # ── 共享色阶：A 和 B 用同一 vmax（取两者中最大值），差异才可见 ──
    shared_vmax = max((max(f.values()) if f else 0) for f in flows)
    shared_vmax = max(shared_vmax, 1)
    if log_scale:
        shared_norm = mcolors.LogNorm(vmin=1, vmax=shared_vmax)
    else:
        shared_norm = mcolors.Normalize(vmin=0, vmax=shared_vmax)
    cmap = matplotlib.colormaps.get_cmap(cmap_name)

    zone_kw = dict(zone_edges=zone_edges, zone_juncs=zone_juncs,
                   node_pos=node_pos, zone_center=zone_center)

    # ════════════════════════════════════════════════════════════════
    #  布局：
    #  单文件:  [全图]
    #  双文件:
    #    行1(全图): A | B | 差值
    #    行2(放大): A-zoom | B-zoom | 差值-zoom  (仅当提供 zone 时)
    # ════════════════════════════════════════════════════════════════
    aspect = (full_bbox[3] - full_bbox[1]) / max(full_bbox[2] - full_bbox[0], 1)

    if not compare:
        fig, ax = plt.subplots(1, 1, figsize=(figwidth * 0.6, figwidth * 0.6 * aspect + 0.8),
                               facecolor=BG)
        fig.suptitle('Traffic Flow Heatmap', color='white', fontsize=13,
                     fontweight='bold', y=0.98)
        draw_flow(ax, edge_shapes, flows[0], shared_norm, cmap, full_bbox,
                  title=titles[0] if titles else os.path.basename(route_files[0]),
                  **zone_kw)
        add_shared_colorbar(fig, [ax], shared_norm, cmap,
                            label='vehicles (log)' if log_scale else 'vehicles')
    else:
        n_rows = 2 if (has_zone and zbbox) else 1
        n_cols = 3   # A | B | Diff

        # 计算放大行的高宽比
        if n_rows == 2:
            zbw = zbbox[2] - zbbox[0]
            zbh = zbbox[3] - zbbox[1]
            zoom_aspect = zbh / max(zbw, 1)
            full_aspect = aspect
            # 两行高度比 = 全图行 : 放大行
            height_ratios = [full_aspect, zoom_aspect]
        else:
            height_ratios = [1]

        col_w = figwidth / n_cols
        fig_h = sum(col_w * r for r in height_ratios) + 1.5
        fig = plt.figure(figsize=(figwidth, fig_h), facecolor=BG)
        gs = gridspec.GridSpec(n_rows, n_cols, figure=fig,
                               height_ratios=height_ratios,
                               hspace=0.08, wspace=0.04)

        t_a = titles[0] if titles and len(titles) > 0 else os.path.basename(route_files[0])
        t_b = titles[1] if titles and len(titles) > 1 else os.path.basename(route_files[1])

        # ── 行1：全图 ──
        ax_a  = fig.add_subplot(gs[0, 0])
        ax_b  = fig.add_subplot(gs[0, 1])
        ax_d  = fig.add_subplot(gs[0, 2])

        draw_flow(ax_a, edge_shapes, flows[0], shared_norm, cmap,
                  full_bbox, title=t_a, **zone_kw)
        draw_flow(ax_b, edge_shapes, flows[1], shared_norm, cmap,
                  full_bbox, title=t_b, **zone_kw)
        draw_diff(ax_d, edge_shapes, flows[0], flows[1],
                  full_bbox, title='Difference  (B − A)',
                  **zone_kw)

        # 全图行共享 colorbar（A 和 B 用同一 norm，差值图有自己的 colorbar）
        add_shared_colorbar(fig, [ax_a, ax_b], shared_norm, cmap,
                            label='vehicles (log)' if log_scale else 'vehicles')

        # ── 行2：区域放大 ──
        if n_rows == 2:
            ax_za = fig.add_subplot(gs[1, 0])
            ax_zb = fig.add_subplot(gs[1, 1])
            ax_zd = fig.add_subplot(gs[1, 2])

            # 放大行用独立色阶（只看区域内）——突出区域内部差异
            zone_flow_max = max(
                (max((flows[i].get(e, 0) for e in zone_edges), default=0)
                 for i in range(2)),
                default=1
            )
            zone_flow_max = max(zone_flow_max, 1)
            if log_scale:
                z_norm = mcolors.LogNorm(vmin=1, vmax=zone_flow_max)
            else:
                z_norm = mcolors.Normalize(vmin=0, vmax=zone_flow_max)

            draw_flow(ax_za, edge_shapes, flows[0], z_norm, cmap,
                      zbbox, title=f'{t_a}  [Zone ×zoom]',
                      highlight_zone=False, **zone_kw)
            draw_flow(ax_zb, edge_shapes, flows[1], z_norm, cmap,
                      zbbox, title=f'{t_b}  [Zone ×zoom]',
                      highlight_zone=False, **zone_kw)
            draw_diff(ax_zd, edge_shapes, flows[0], flows[1],
                      zbbox, title='Difference  [Zone ×zoom]',
                      **zone_kw)

            add_shared_colorbar(fig, [ax_za, ax_zb], z_norm, cmap,
                                label='zone vehicles (log)' if log_scale else 'zone vehicles')

        fig.suptitle('Road Network Traffic Flow Comparison',
                     color='white', fontsize=14, fontweight='bold', y=1.005)

    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    fig.savefig(output_file, dpi=180, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[完成] 已保存: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='SUMO 路网流量热力图')
    parser.add_argument('-n', '--net',    required=True)
    parser.add_argument('-r', '--routes', nargs='+', required=True)
    parser.add_argument('-o', '--output', default='tools/output/flow_viz.png')
    parser.add_argument('--titles',       nargs='+', default=None)
    parser.add_argument('--zone',         default=None)
    parser.add_argument('--time_limit',   type=float, default=None)
    parser.add_argument('--log',          action='store_true',
                        help='使用对数色阶（默认线性）')
    parser.add_argument('--cmap',         default='hot_r')
    parser.add_argument('--figwidth',     type=float, default=20.0)
    args = parser.parse_args()

    for f in [args.net] + args.routes:
        if not os.path.exists(f):
            sys.exit(f"错误: 文件不存在: {f}")

    visualize(
        net_file    = args.net,
        route_files = args.routes,
        output_file = args.output,
        titles      = args.titles,
        time_limit  = args.time_limit,
        zone_file   = args.zone,
        log_scale   = args.log,
        cmap_name   = args.cmap,
        figwidth    = args.figwidth,
    )


if __name__ == '__main__':
    main()
