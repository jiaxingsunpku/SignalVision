"""SV→ANP 感知归并与 phase 拓扑（task5，第一步方向级）。

依赖 SV `world.intersections` 的真实几何：
- `directions`=road 朝向角(atan2,0=北/π⁄2=东/π=南/3π⁄2=西)、`outs`=road 进/出、
  `road_lane_mapping`=road→lanes、`phase_available_lanelinks`=phase→(进,出)lane 对。

产出：
1. lane→方向（几何角→罗盘 N/S/E/W）+ per-junction 进口 lane 按方向分组（每步聚合观测用）。
2. per-junction phase→放行方向集合 + n_phases（导出给执行体，C-1 过渡：写 JSON）。

注：归并为方向级是第一步务实取舍（followups A-1，贴合第二步摄像头粒度）。
"""

import json
import math
import os

_TOPOLOGY_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), ".anp_topology.json")


def topology_path():
    """phase 拓扑共享文件路径（C-1 过渡；SV host 写、执行体读，同机）。"""
    return os.environ.get("ANP_SV_TOPOLOGY_PATH", _TOPOLOGY_PATH_DEFAULT)


def angle_to_compass(angle):
    """SV road 朝向角(atan2(x,y) 弧度) → 罗盘方向。0=北 π⁄2=东 π=南 3π⁄2=西。"""
    a = angle % (2 * math.pi)
    if a < math.pi / 4 or a >= 7 * math.pi / 4:
        return "north"
    if a < 3 * math.pi / 4:
        return "east"
    if a < 5 * math.pi / 4:
        return "south"
    return "west"


class SvAnpTopology:
    """从 SV world.intersections 构建一次（初始化时），供每步观测聚合 + 导出执行体拓扑。"""

    def __init__(self, world, junction_filter=None):
        self.incoming_by_direction = {}  # iid -> {direction: [lane_id]}（仅进口）
        self.phase_directions = {}       # iid -> [set(direction)]（按 phase index）
        self.n_phases = {}               # iid -> int
        # task5 路 A：限定到 sv-network(have_tl)路口集合，保证前端 100% 认领定位（A-4 对齐）
        self._filter = set(str(x) for x in junction_filter) if junction_filter is not None else None
        self._build(world)

    def _build(self, world):
        for inter in world.intersections:
            iid = inter.id
            if self._filter is not None and str(iid) not in self._filter:
                continue  # 不在 sv-network(have_tl)集合的路口跳过（A-4 对齐）
            lane_dir = {}   # 进口 lane_id -> direction
            by_dir = {}
            for i, road in enumerate(inter.roads):
                if i < len(inter.outs) and inter.outs[i]:
                    continue  # 出口 road 跳过（maxpressure 用进口）
                if i >= len(inter.directions):
                    continue
                direction = angle_to_compass(inter.directions[i])
                for lane in inter.road_lane_mapping.get(road, []):
                    lane_dir[lane] = direction
                    by_dir.setdefault(direction, []).append(lane)
            self.incoming_by_direction[iid] = by_dir

            phase_dirs = []
            lanelinks = getattr(inter, "phase_available_lanelinks", [])
            for phase_id in range(len(inter.phases)):
                dirs = set()
                if phase_id < len(lanelinks):
                    for pair in lanelinks[phase_id]:
                        start = pair[0] if pair else None
                        d = lane_dir.get(start)
                        if d:
                            dirs.add(d)
                phase_dirs.append(dirs)
            self.phase_directions[iid] = phase_dirs
            self.n_phases[iid] = len(inter.phases)

    def export(self):
        """per-junction 拓扑 dict（供执行体方向级 max-pressure：phase→放行方向集合）。"""
        return {
            iid: {
                "n_phases": self.n_phases[iid],
                "phase_directions": [sorted(s) for s in self.phase_directions[iid]],
                "directions": sorted(self.incoming_by_direction.get(iid, {}).keys()),
            }
            for iid in self.n_phases
        }

    def write_json(self, path=None):
        path = path or topology_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.export(), f, ensure_ascii=False, indent=2)
            return path
        except Exception:
            return None


def aggregate_observations(topology, lane_data):
    """每步：按拓扑把 subscription_cache['lane_data'] 聚合成 per-junction 方向级 approaches。

    lane_data: {lane_id: {vehicle_number, mean_speed, occupancy, halting_number}}。
    返回 {intersection_id: [approach dict{direction,vehicle_count,halting_count,mean_speed_mps}]}。
    （vehicle_count=瞬时车数，followups A-2 过渡语义。）
    """
    result = {}
    for iid, by_dir in topology.incoming_by_direction.items():
        approaches = []
        for direction, lanes in by_dir.items():
            vc = hc = 0
            sp_sum = 0.0
            sp_n = 0
            for lane in lanes:
                d = lane_data.get(lane)
                if not d:
                    continue
                n = int(d.get("vehicle_number", 0))
                vc += n
                hc += int(d.get("halting_number", 0))
                if n > 0:
                    sp_sum += float(d.get("mean_speed", 0.0)) * n
                    sp_n += n
            approaches.append({
                "direction": direction,
                "vehicle_count": vc,
                "halting_count": hc,
                "mean_speed_mps": (sp_sum / sp_n) if sp_n > 0 else 0.0,
            })
        if approaches:  # ObservationPayload.approaches 要求非空
            result[iid] = approaches
    return result
