"""ANP Kafka 接入（task5）：SV 作为边缘节点接入 ANP 分层黑板的传输层。

职责：把 SV 的 per-junction 感知发到 ANP 观测 topic、订阅 control 层相位注入、自注册 + 心跳。
**不 import anp 包**（SV 独立 env，Py3.8），按 ANP envelope/payload schema 手工构造 dict
（对齐 backend/anp/contracts，docs/protocol.md §1）。

**降级红线（task5 A4）**：所有 Kafka 调用一律 try/except 吞错、**绝不把异常抛进仿真线程**；
Kafka 不可达时 producer/consumer 静默 no-op，SV 仍用内置算法自闭环。
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

try:
    from confluent_kafka import Consumer, Producer
    _KAFKA_OK = True
except Exception:  # pragma: no cover - 降级：未装 confluent-kafka
    _KAFKA_OK = False

SCHEMA_VERSION = "1.0"

# ANP topic（与 backend/anp/contracts/topics.py 一致，勿在别处散改）
TOPIC_OBSERVATION = "anp.traffic.perception.observation.v1"
TOPIC_STATUS = "anp.traffic.status.intersection.v1"
TOPIC_CONTROL_PHASE = "anp.traffic.control.phase.v1"
TOPIC_WORLD_LIFECYCLE = "anp.world.agent.lifecycle.v1"
TOPIC_WORLD_HEARTBEAT = "anp.world.agent.heartbeat.v1"


def _bootstrap():
    return os.environ.get("ANP_BOOTSTRAP", "localhost:9092")


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _uuid():
    return str(uuid.uuid4())


def wall_age_seconds(event_ts):
    """event_ts(ISO8601 UTC 带 Z) 到现在的挂钟秒数(世界时钟 v1 新鲜度判据);解析失败返回 None。

    SV 为 Py3.8,fromisoformat 不认 'Z',先换成 '+00:00'。
    """
    if not event_ts:
        return None
    try:
        dt = datetime.fromisoformat(str(event_ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return None


def _envelope(event_type, source_agent_id, payload, object_id=None,
              source_system="collaborative_agent", sequence=0):
    """统一 envelope dict（对齐 anp.contracts.Envelope.to_wire，含显式 null 便于消费侧稳定解析）。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "message_id": _uuid(),
        "event_type": event_type,
        "source": {"system": source_system, "agent_id": source_agent_id, "gateway_id": None},
        "target": {"agent_id": None, "region_id": None},
        "time": {"event_ts": _now_iso(), "sequence": int(sequence), "expires_at": None},
        "scope": {"site_id": None, "region_id": None, "object_id": object_id},
        "payload": payload,
        "quality": {"confidence": 1.0, "data_latency_ms": 0},
        "trace": {"trace_id": _uuid(), "parent_trace_id": None},
    }


def observation_envelope(agent_id, intersection_id, approaches, sim_time, sim_step, sequence=0):
    """per-junction 观测 envelope。

    approaches: list of dict{direction, vehicle_count, halting_count, mean_speed_mps}。
    注（task5 过渡，见 followups A-2）：vehicle_count 第一步填**瞬时车数**（maxpressure 需），非吞吐原义。
    """
    payload = {
        "observation_type": "traffic.intersection",
        "intersection_id": intersection_id,
        "approaches": [
            {
                "direction": a["direction"],
                "vehicle_count": int(a["vehicle_count"]),
                "halting_count": int(a["halting_count"]),
                "mean_speed_mps": float(a["mean_speed_mps"]),
                "mean_delay_sec": None,
            }
            for a in approaches
        ],
        "sim_clock": {"sim_time": float(sim_time), "sim_step": int(sim_step)},
    }
    return _envelope("observation.traffic.intersection", agent_id, payload, object_id=intersection_id,
                     sequence=sequence)


def lifecycle_envelope(agent_id, agent_type, registered, capabilities=None,
                       command_types=None, members=None, produces=None, consumes=None):
    """注册/下线 envelope（topic anp.world.agent.lifecycle.v1，统一世界名册）。"""
    payload = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "capabilities": list(capabilities or []),
        "command_types": list(command_types or []),
        "produces": list(produces or []),
        "consumes": list(consumes or []),
        "weight": 1.0,
        "members": list(members or []),
    }
    et = "agent.registered" if registered else "agent.deregistered"
    src_sys = "platform" if agent_type == "model" else "collaborative_agent"
    return _envelope(et, agent_id, payload, source_system=src_sys)


def heartbeat_envelope(agent_id, status="online", last_error=None, metadata=None):
    """心跳 envelope（topic anp.world.agent.heartbeat.v1）。metadata 带 agent 自报元信息（task5 P-10）。"""
    return _envelope("agent.heartbeat", agent_id,
                     {"status": status, "last_error": last_error, "metadata": metadata or {}})


def signal_phase_envelope(agent_id, intersection_id, phase_index, based_on_sim_step,
                          based_on_sim_time=None, based_on_event_ts=None):
    """控制层相位注入 envelope（topic anp.traffic.control.phase.v1）。执行体→SV 写灯口。

    ``based_on_event_ts``(世界时钟 v1):决策所基于观测的事件挂钟,写灯口据此算挂钟 age 判过期。
    """
    payload = {
        "control_type": "signal.phase",
        "intersection_id": str(intersection_id),
        "phase_index": int(phase_index),
        "based_on_sim_step": int(based_on_sim_step),
        "based_on_sim_time": (float(based_on_sim_time) if based_on_sim_time is not None else None),
        "based_on_event_ts": (str(based_on_event_ts) if based_on_event_ts else None),
    }
    return _envelope("control.traffic.phase", agent_id, payload, object_id=str(intersection_id))


def parse_signal_phase(value):
    """解析 control.phase → (intersection_id, phase_index, based_on_sim_step, based_on_event_ts);失败 None。"""
    try:
        if value.get("event_type") != "control.traffic.phase":
            return None
        p = value.get("payload") or {}
        return (str(p["intersection_id"]), int(p["phase_index"]), int(p["based_on_sim_step"]),
                p.get("based_on_event_ts"))
    except Exception:
        return None


class AnpProducer:
    """confluent-kafka producer 薄封装：produce 异步入队、全程吞错；Kafka 不可达不阻塞仿真。"""

    def __init__(self, bootstrap=None):
        self._p = None
        if not _KAFKA_OK:
            return
        try:
            self._p = Producer({
                "bootstrap.servers": bootstrap or _bootstrap(),
                "queue.buffering.max.messages": 1000000,
                "linger.ms": 20,
            })
        except Exception:
            self._p = None

    @property
    def available(self):
        return self._p is not None

    def publish(self, topic, key, envelope):
        if self._p is None:
            return
        try:
            self._p.produce(topic, value=json.dumps(envelope).encode("utf-8"),
                            key=(key or "").encode("utf-8"))
            self._p.poll(0)
        except BufferError:
            try:
                self._p.poll(0.1)
            except Exception:
                pass
        except Exception:
            pass

    def flush(self, timeout=2.0):
        if self._p is None:
            return
        try:
            self._p.flush(timeout)
        except Exception:
            pass


class AnpRegistrar:
    """host agent + per-junction agents 注册 + 周期心跳 + 下线（task5 路 A）。

    host 自报 members；同时为每个 per-junction agent 发独立 lifecycle（带 produces/consumes
    channel keys=路口 id，供前端按 key 认领图上 junction、定位到真实路口）+ 心跳。
    daemon 心跳线程，全程吞错。走 world 域名册（registry 同时订阅 world + traffic 域）。

    junction_agents: list of dict{agent_id, agent_type, capabilities, produces?, consumes?}。
    """

    def __init__(self, producer, agent_id, agent_type, capabilities,
                 command_types=None, members=None, interval=5.0, junction_agents=None,
                 metadata_provider=None):
        self.producer = producer
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capabilities = list(capabilities or [])
        self.command_types = list(command_types or [])
        self.members = list(members or [])
        self.interval = interval
        self.junction_agents = list(junction_agents or [])
        self.metadata_provider = metadata_provider  # callable → dict（task5 P-10：host 自报仿真元信息）
        self._stop = threading.Event()
        self._thread = None

    def _emit_lifecycle(self, registered):
        try:
            env = lifecycle_envelope(self.agent_id, self.agent_type, registered,
                                     capabilities=self.capabilities, command_types=self.command_types,
                                     members=self.members)
            self.producer.publish(TOPIC_WORLD_LIFECYCLE, self.agent_id, env)
            for ja in self.junction_agents:
                jenv = lifecycle_envelope(ja["agent_id"], ja.get("agent_type", "signalvision"), registered,
                                          capabilities=ja.get("capabilities"),
                                          produces=ja.get("produces"), consumes=ja.get("consumes"))
                self.producer.publish(TOPIC_WORLD_LIFECYCLE, ja["agent_id"], jenv)
            self.producer.flush()
        except Exception:
            pass

    def start(self):
        self._emit_lifecycle(True)
        self.emit_heartbeat("online")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def emit_heartbeat(self, status="online"):
        """立即发送一帧 host + per-junction 心跳。用于启动间隔外的状态收敛。"""
        try:
            meta = {}
            if self.metadata_provider:
                try:
                    meta = self.metadata_provider() or {}
                except Exception:
                    meta = {}
            self.producer.publish(TOPIC_WORLD_HEARTBEAT, self.agent_id,
                                  heartbeat_envelope(self.agent_id, status, metadata=meta))
            for ja in self.junction_agents:
                self.producer.publish(TOPIC_WORLD_HEARTBEAT, ja["agent_id"],
                                      heartbeat_envelope(ja["agent_id"], status))
            self.producer.flush()
        except Exception:
            pass

    def _run(self):
        while not self._stop.wait(self.interval):
            self.emit_heartbeat("online")

    def stop(self):
        self._stop.set()
        self.emit_heartbeat("offline")
        self._emit_lifecycle(False)


class AnpPhaseConsumer:
    """后台线程订阅 control.phase，维护 per-junction 最新相位槽（线程安全）。供 SV 写灯口读（P-3）。"""

    def __init__(self, bootstrap=None, group_id=None):
        self._slot = {}  # intersection_id -> (phase_index, based_on_sim_step, recv_wall)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._c = None
        if not _KAFKA_OK:
            return
        try:
            self._c = Consumer({
                "bootstrap.servers": bootstrap or _bootstrap(),
                "group.id": group_id or ("anp-sv-phase-" + _uuid()[:8]),
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
            })
            self._c.subscribe([TOPIC_CONTROL_PHASE])
        except Exception:
            self._c = None

    @property
    def available(self):
        return self._c is not None

    def start(self):
        if self._c is None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                msg = self._c.poll(0.5)
                if msg is None or msg.error():
                    continue
                value = json.loads(msg.value().decode("utf-8"))
                parsed = parse_signal_phase(value)
                if parsed is None:
                    continue
                iid, phase_index, based_on, based_ts = parsed
                with self._lock:
                    self._slot[iid] = (phase_index, based_on, based_ts, time.time())
            except Exception:
                continue

    def get_latest(self, intersection_id):
        """返回该路口最新相位 (phase_index, based_on_sim_step, recv_wall)，无则 None。"""
        with self._lock:
            return self._slot.get(intersection_id)

    def stop(self):
        self._stop.set()
        if self._c is not None:
            try:
                self._c.close()
            except Exception:
                pass
