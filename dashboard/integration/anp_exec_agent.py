"""ANP 信号控制执行体（task5 P-5，SV 仓库内独立进程）。

决策外置：订阅 ANP **状态 topic** → per-junction 方向级 max-pressure → 发相位指令到 control.phase。
输入完全来自 ANP（为第二步摄像头留钩子，followups I-1）；phase→方向拓扑读共享 JSON（C-1 过渡）。
**不 import anp 包**；Kafka 失败吞错；某路口无 phase 拓扑/状态则不发（让 SV 写灯口回落内置算法）。

方向级 max-pressure（followups B-1 近似）：pressure(phase)=Σ 放行方向的 queue_length_m，选 max。
用法::

    python dashboard/integration/anp_exec_agent.py [--bootstrap localhost:9092] [--duration 0]
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # PROJECT_ROOT

from confluent_kafka import Consumer
from dashboard.integration.anp_kafka import (
    AnpProducer, AnpRegistrar, signal_phase_envelope, TOPIC_CONTROL_PHASE, TOPIC_STATUS, _bootstrap, _uuid,
)
from dashboard.integration.anp_sensing import topology_path

EXEC_PREFIX = os.environ.get("ANP_SV_EXEC_PREFIX", "traffic-exec-sv-j")


class AnpExecAgent:
    """方向级 max-pressure 决策（吃 ANP 状态的 queue_length_m + phase→方向拓扑）。"""

    def __init__(self, topology):
        self.phase_dirs = {iid: [set(d) for d in t["phase_directions"]] for iid, t in topology.items()}
        self.n_phases = {iid: t["n_phases"] for iid, t in topology.items()}

    def decide(self, iid, queue_by_dir):
        """返回目标 phase_index；无拓扑/单相位返回 None（不注入，让 SV 回落内置）。"""
        phase_dirs = self.phase_dirs.get(iid)
        if not phase_dirs or len(phase_dirs) < 2:
            return None
        best, best_p = None, None
        for pid, dirs in enumerate(phase_dirs):
            pressure = sum(queue_by_dir.get(d, 0.0) for d in dirs)
            if best_p is None or pressure > best_p:
                best_p, best = pressure, pid
        return best


def main():
    ap = argparse.ArgumentParser(description="ANP 信号控制执行体（task5）")
    ap.add_argument("--bootstrap", default=None)
    ap.add_argument("--duration", type=float, default=0, help="运行秒数，0=永久")
    args = ap.parse_args()

    path = topology_path()
    if not os.path.exists(path):
        print("[exec] phase 拓扑文件不存在，请先起 SV host 生成: " + path)
        return 1
    with open(path, encoding="utf-8") as f:
        topology = json.load(f)
    agent = AnpExecAgent(topology)
    producer = AnpProducer(args.bootstrap)
    members = [EXEC_PREFIX + str(iid) for iid in topology]
    # task5 路 A：每路口一个独立执行 agent，consumes 状态 / produces 相位 通道 keys=路口 id → 前端定位真实路口
    junction_agents = [
        {"agent_id": EXEC_PREFIX + str(iid), "agent_type": "signalvision", "capabilities": ["exec"],
         "consumes": [{"topic": TOPIC_STATUS, "keys": [str(iid)]}],
         "produces": [{"topic": TOPIC_CONTROL_PHASE, "keys": [str(iid)]}]}
        for iid in topology
    ]
    registrar = AnpRegistrar(producer, "traffic-exec-sv-host-001", "exec", ["exec"],
                             members=members, junction_agents=junction_agents)
    registrar.start()
    consumer = Consumer({
        "bootstrap.servers": args.bootstrap or _bootstrap(),
        "group.id": "anp-exec-" + _uuid()[:8],
        "auto.offset.reset": "latest",
    })
    consumer.subscribe([TOPIC_STATUS])
    print("[exec] 启动：%d 路口拓扑，订阅 %s，producer=%s"
          % (len(topology), TOPIC_STATUS, "on" if producer.available else "off"))

    sent = 0
    t0 = time.time()
    try:
        while True:
            if args.duration and time.time() - t0 > args.duration:
                break
            msg = consumer.poll(0.5)
            if msg is None or msg.error():
                continue
            try:
                v = json.loads(msg.value().decode("utf-8"))
                if v.get("event_type") != "status.traffic.intersection":
                    continue
                p = v["payload"]
                iid = p["intersection_id"]
                queue_by_dir = {a["direction"]: float(a.get("queue_length_m", 0.0))
                                for a in p.get("approaches", [])}
                sc = p.get("sim_clock") or {}
                sim_step = int(sc.get("sim_step", 0))
                origin_event_ts = (v.get("time") or {}).get("event_ts")  # 世界时钟 v1：透传观测事件挂钟
                phase = agent.decide(iid, queue_by_dir)
                if phase is None:
                    continue
                env = signal_phase_envelope(EXEC_PREFIX + str(iid), iid, phase, sim_step,
                                            sc.get("sim_time"), based_on_event_ts=origin_event_ts)
                producer.publish(TOPIC_CONTROL_PHASE, str(iid), env)
                sent += 1
                if sent % 200 == 0:
                    print("[exec] sent=%d" % sent)
            except Exception:
                continue
    finally:
        try:
            registrar.stop()
        except Exception:
            pass
        producer.flush()
        consumer.close()
        print("[exec] 结束 sent=%d" % sent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
