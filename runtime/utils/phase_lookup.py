from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class PhaseLookup:
    """查询某个路口在一天中某一秒所处的车辆相位。

    约定：
    1. second_of_day 的取值是 [0, 86400) 内的一天秒数；超出范围会自动取模。
    2. 相位差 offset_s 按“日内绝对秒”解释：pos = (t - offset_s) % cycle_s
    3. period 区间是左闭右开 [start_s, end_s)
    4. 若 period 不可用（原始数据缺失），返回 None
    5. phase_id = 0 表示“无车辆放行”或“源数据不一致时补齐的空档”
    """

    def __init__(self, json_path: str | Path):
        self.json_path = Path(json_path)
        with self.json_path.open("r", encoding="utf-8") as f:
            self.data: dict[str, Any] = json.load(f)

        self.intersections: dict[str, Any] = self.data["intersections"]
        self.phase_labels: dict[int, str] = {
            int(k): v for k, v in self.data["phase_labels"].items()
        }

    def _get_period(
        self,
        intersection_id: str,
        second_of_day: int,
        plan: Optional[str] = None,
    ) -> tuple[dict[str, Any], dict[str, Any], int, str]:
        if intersection_id not in self.intersections:
            raise KeyError(f"未知路口 id: {intersection_id}")

        intersection = self.intersections[intersection_id]
        selected_plan = plan or intersection["default_plan"]

        if selected_plan not in intersection["plans"]:
            available = ", ".join(intersection["plans"].keys())
            raise KeyError(
                f"路口 {intersection_id} 不存在 plan={selected_plan}，可选值: {available}"
            )

        t = second_of_day % 86400
        periods = intersection["plans"][selected_plan]

        for period in periods:
            if period["start_s"] <= t < period["end_s"]:
                return intersection, period, t, selected_plan

        raise ValueError(
            f"时间 {second_of_day} 秒未命中任何时段，"
            f"这通常说明 JSON 的时段覆盖不完整。"
        )

    def get_phase(
        self,
        intersection_id: str,
        second_of_day: int,
        plan: Optional[str] = None,
    ) -> Optional[int]:
        """返回 phase_id。

        对于大多数路口，直接传 intersection_id 和 second_of_day 即可。
        少数同时区分 weekday/weekend 的路口，如果不传 plan，会默认使用 JSON 里的 default_plan。
        """
        _, period, t, _ = self._get_period(intersection_id, second_of_day, plan)

        if not period["available"]:
            return None

        cycle_s = int(period["cycle_s"])
        offset_s = int(period["offset_s"] or 0)

        # 如果你的控制器把相位差定义为“相对当前时段起点”，
        # 把下一行改成：
        # pos_in_cycle = (t - period["start_s"] - offset_s) % cycle_s
        pos_in_cycle = (t - offset_s) % cycle_s

        acc = 0
        for phase_id, duration_s in period["stages"]:
            acc += int(duration_s)
            if pos_in_cycle < acc:
                return int(phase_id)

        # 理论上不会到这里；作为兜底，返回最后一个阶段的相位。
        return int(period["stages"][-1][0]) if period["stages"] else None

    def get_phase_info(
        self,
        intersection_id: str,
        second_of_day: int,
        plan: Optional[str] = None,
    ) -> dict[str, Any]:
        """返回更完整的信息，便于调试。"""
        intersection, period, t, selected_plan = self._get_period(
            intersection_id, second_of_day, plan
        )
        phase_id = self.get_phase(intersection_id, second_of_day, selected_plan)

        return {
            "intersection_id": intersection_id,
            "intersection_name": intersection["name"],
            "plan": selected_plan,
            "second_of_day": t,
            "period_start_s": period["start_s"],
            "period_end_s": period["end_s"],
            "available": period["available"],
            "cycle_s": period["cycle_s"],
            "offset_s": period["offset_s"],
            "phase_id": phase_id,
            "phase_name": self.phase_labels.get(phase_id) if phase_id is not None else None,
        }


if __name__ == "__main__":
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="查询某路口在某一秒所处的车辆相位")
    parser.add_argument("intersection_id", help="例如 J001")
    parser.add_argument("second_of_day", type=int, help="一天中的第多少秒，例如 8:30:00 = 30600")
    parser.add_argument(
        "--json",
        default="sumo_signal_reference_ezhou_vehicle_compact.json",
        help="JSON 文件路径",
    )
    parser.add_argument(
        "--plan",
        default=None,
        help="可选: all_days / weekday / weekend；不传则使用 JSON 中的 default_plan",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="输出完整调试信息，而不只是 phase_id",
    )
    args = parser.parse_args()

    lookup = PhaseLookup(args.json)

    if args.info:
        print(
            _json.dumps(
                lookup.get_phase_info(args.intersection_id, args.second_of_day, args.plan),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(lookup.get_phase(args.intersection_id, args.second_of_day, args.plan))
