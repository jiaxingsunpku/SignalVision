"""
LibSignal 运行时适配器

将搬运进 rebuild/runtime 的 LibSignal 原始运行内核，
封装成 Dashboard 期望的标准接口。
"""

import logging
import os
import subprocess
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from .config_converter import ConfigConverter
from .network_data_loader import load_network_from_runtime
from .standard_interface import StandardArgs, StandardInterface, StandardSimulation, StandardSolver


RUNTIME_ROOT = Path(__file__).parent.parent / 'runtime'
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

_libsignal_imported = False
_import_error = None


def _clear_libsignal_modules():
    """清理通用顶级模块名，避免和宿主进程中的其他包冲突。"""
    managed_prefixes = (
        'common',
        'utils',
        'agent',
        'dataset',
        'task',
        'runner',
        'trainer',
        'world',
    )
    stale_keys = []
    for name in list(sys.modules.keys()):
        if name in managed_prefixes or name.startswith(tuple(f"{prefix}." for prefix in managed_prefixes)):
            stale_keys.append(name)
    for name in stale_keys:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


def _load_inner_package(module_name: str):
    """从 rebuild/runtime 目录显式加载顶级包，避免和宿主进程同名目录冲突。"""
    package_dir = RUNTIME_ROOT / module_name
    init_file = package_dir / '__init__.py'
    if not init_file.exists():
        raise ImportError(f"LibSignal 包不存在: {module_name} ({init_file})")

    spec = importlib.util.spec_from_file_location(
        module_name,
        init_file,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法创建 LibSignal 包规格: {module_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _import_libsignal():
    """延迟导入 LibSignal 原始模块，保证注册副作用生效。"""
    global _libsignal_imported, _import_error

    if _libsignal_imported:
        return True

    try:
        global Registry, interface_module, build_config, setup_logging

        _clear_libsignal_modules()

        from common.registry import Registry
        from common import interface as interface_module
        from utils.logger import build_config, setup_logging

        importlib.import_module('agent')
        importlib.import_module('dataset')
        importlib.import_module('task')
        importlib.import_module('task.task')
        _load_inner_package('runner')
        importlib.import_module('runner.base_runner')
        importlib.import_module('runner.tsc_runner')
        importlib.import_module('world')

        missing = []
        if 'tsc' not in Registry.mapping['task_mapping']:
            missing.append(
                f"task_mapping 缺少 tsc，当前 keys={sorted(Registry.mapping['task_mapping'].keys())}"
            )
        if 'tsc' not in Registry.mapping['trainer_mapping']:
            missing.append(
                f"trainer_mapping 缺少 tsc，当前 keys={sorted(Registry.mapping['trainer_mapping'].keys())}"
            )
        if missing:
            raise ImportError("LibSignal 注册不完整: " + "; ".join(missing))

        _libsignal_imported = True
        return True
    except Exception as exc:  # pragma: no cover - 运行期依赖错误
        _import_error = exc
        return False


def create_libsignal_args(std_args: StandardArgs):
    """创建 LibSignal 原始参数对象。"""
    return ConfigConverter.standard_to_libsignal(std_args)


class LibSignalSimulation(StandardSimulation):
    """
    LibSignal 仿真适配器。
    """

    def __init__(self, args: StandardArgs, nogui: bool = True):
        if not _import_libsignal():
            raise ImportError(f"无法导入 LibSignal 模块: {_import_error}")

        self.std_args = args
        self.nogui = nogui
        self.libsignal_args = create_libsignal_args(args)

        self.config = None
        self.logger = None
        self.trainer = None
        self.world = None
        self.agents = None
        self.env = None
        self.metric = None

        self._initialized = False
        self._started = False
        self._interface = None
        self._signal_complete = False
        self._vehiclegen = None
        self._pending_actions = None
        self.step_count = 0
        self.traffic_metrics = {
            'departed_step': 0,
            'arrived_step': 0,
            'departed_total': 0,
            'arrived_total': 0,
            'active_vehicles': 0,
        }

        print(
            f"[LibSignalSimulation] 初始化完成: world={self.libsignal_args.world}, "
            f"network={self.libsignal_args.network}, agent={self.libsignal_args.agent}"
        )

    def _override_runtime_flags(self):
        if getattr(self.libsignal_args, 'gui', None) is not None:
            self.config.setdefault('world', {})['gui'] = bool(self.libsignal_args.gui)
        if getattr(self.libsignal_args, 'flow_file', ''):
            self.config.setdefault('world', {})['flowFile'] = self.libsignal_args.flow_file
        if getattr(self.libsignal_args, 'combined_file', None) is not None:
            self.config.setdefault('world', {})['combined_file'] = self.libsignal_args.combined_file
        if getattr(self.libsignal_args, 'load_model', None) is not None:
            self.config['model']['load_model'] = self.libsignal_args.load_model
        if getattr(self.libsignal_args, 'test_model', None) is not None:
            self.config['model']['test_model'] = self.libsignal_args.test_model
        if getattr(self.libsignal_args, 'train_model', None) is not None:
            self.config['model']['train_model'] = self.libsignal_args.train_model
        if getattr(self.libsignal_args, 'load_episode', None) is not None:
            self.config['trainer']['episodes'] = self.libsignal_args.load_episode

        if self.config['model'].get('test_model') and 'epsilon' in self.config['model']:
            self.config['model']['epsilon'] = 0.0

    def _register_config(self):
        interface_module.Command_Setting_Interface(self.config)
        interface_module.Logger_param_Interface(self.config)
        interface_module.World_param_Interface(self.config)
        if self.config['model'].get('graphic', False):
            param = Registry.mapping['world_mapping']['setting'].param
            if self.config['command']['world'] in {'sumo', 'cityflow'}:
                roadnet_path = param['dir'] + param['roadnetFile']
            else:
                roadnet_path = param['road_file_addr']
            interface_module.Graph_World_Interface(roadnet_path)
        interface_module.Logger_path_Interface(self.config)
        output_path = Registry.mapping['logger_mapping']['path'].path
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        interface_module.Trainer_param_Interface(self.config)
        interface_module.ModelAgent_param_Interface(self.config)

    def _load_models_if_needed(self):
        if not self.config['model'].get('load_model', False):
            print("[LibSignalSimulation] 跳过模型加载 (load_model=False)")
            return

        if not self.agents or not hasattr(self.agents[0], 'load_model'):
            print(f"[LibSignalSimulation] {self.config['command']['agent']} 不支持模型加载")
            return

        load_episode = self.config['trainer'].get('episodes', 200)
        print(f"[LibSignalSimulation] 准备加载模型: epoch={load_episode}")
        for agent in self.agents:
            agent.load_model(load_episode)
        print(f"[LibSignalSimulation] 模型加载完成: {len(self.agents)} 个 agents")

    def gen_sim(self):
        if self._initialized:
            return

        original_dir = os.getcwd()
        try:
            os.chdir(RUNTIME_ROOT)
            self.config, _ = build_config(self.libsignal_args)
            self._override_runtime_flags()
            self._register_config()

            self.logger = setup_logging(logging.INFO)
            trainer_class = Registry.mapping['trainer_mapping'][self.config['command']['task']]
            self.trainer = trainer_class(self.logger)

            self.world = self.trainer.world
            self.agents = self.trainer.agents
            self.metric = self.trainer.metric
            self.env = self.trainer.env
            self._load_models_if_needed()

            self._initialized = True
            print(f"[LibSignalSimulation] 仿真环境生成完成: {len(self.world.intersections)} 个路口")
        except Exception as exc:
            raise RuntimeError(f"生成仿真环境失败: {exc}") from exc
        finally:
            os.chdir(original_dir)

    def start(self):
        if not self._initialized:
            self.gen_sim()
        if self._started:
            return

        self.env.reset()
        for agent in self.agents or []:
            reset_fn = getattr(agent, 'reset', None)
            if callable(reset_fn):
                reset_fn()
        self._pending_actions = None
        self.step_count = 0
        self.traffic_metrics.update({
            'departed_step': 0,
            'arrived_step': 0,
            'departed_total': 0,
            'arrived_total': 0,
            'active_vehicles': 0,
        })
        self._started = True
        print("[LibSignalSimulation] 仿真已启动")

    def _sim_step_sumo(self):
        for _ in range(self.world.step_ratio):
            self.world.eng.simulationStep()

        for intersection in self.world.intersections:
            intersection.observe(self.world.step_length, self.world.max_distance)

        entering_v = self.world.eng.simulation.getDepartedIDList()
        exiting_v = self.world.eng.simulation.getArrivedIDList()
        try:
            active_count = len(self.world.eng.vehicle.getIDList())
        except Exception:
            active_count = max(
                0,
                self.traffic_metrics['active_vehicles'] + len(entering_v) - len(exiting_v)
            )
        self.traffic_metrics.update({
            'departed_step': len(entering_v),
            'arrived_step': len(exiting_v),
            'departed_total': self.traffic_metrics['departed_total'] + len(entering_v),
            'arrived_total': self.traffic_metrics['arrived_total'] + len(exiting_v),
            'active_vehicles': active_count,
        })
        for vehicle_id in entering_v:
            self.world.inside_vehicles[vehicle_id] = self.world.eng.simulation.getTime()
        for vehicle_id in exiting_v:
            if vehicle_id in self.world.inside_vehicles:
                self.world.vehicles[vehicle_id] = (
                    self.world.eng.simulation.getTime() - self.world.inside_vehicles[vehicle_id]
                )
                del self.world.inside_vehicles[vehicle_id]

        self.world._update_infos()
        self.world.vehicle_trajectory, self.world.vehicle_maxspeed = self.world.get_vehicle_trajectory()
        self.world.run += 1
        self.step_count = self.world.run

        if self.step_count <= 5:
            try:
                active_count = self.traffic_metrics['active_vehicles']
            except Exception:
                active_count = -1
            try:
                min_expected = self.world.eng.simulation.getMinExpectedNumber()
            except Exception:
                min_expected = -1
            print(
                f"[LibSignalSimulation] SUMO step={self.step_count} "
                f"time={self.world.eng.simulation.getTime()} "
                f"departed={len(entering_v)} arrived={len(exiting_v)} "
                f"active={active_count} min_expected={min_expected}"
            )

    def _sim_step_cityflow(self):
        self.world.step(self._pending_actions)
        self._pending_actions = None
        self.step_count += 1

    def sim_step(self):
        if not self._started:
            raise RuntimeError("仿真未启动，请先调用 start()")

        world_name = self.config['command']['world']
        if world_name == 'cityflow':
            self._sim_step_cityflow()
        else:
            self._sim_step_sumo()

    def update_netdata(self):
        pass

    def update_travel_times(self):
        pass

    def set_interface(self, interface):
        self._interface = interface

    def close(self):
        if self.world is not None and getattr(self.world, 'eng', None) is not None:
            eng = self.world.eng
            close_fn = getattr(eng, 'close', None)
            if callable(close_fn):
                try:
                    if self.config['command']['world'] == 'sumo' and not self.world.interface_flag:
                        # TraCI Connection.close() 默认会无限等待 SUMO-GUI 进程退出。
                        # 先关闭协议连接，再有界地回收由 traci.start() 创建的子进程。
                        process = getattr(eng, '_process', None)
                        close_fn(False)
                        if process is not None and process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=5)
                    else:
                        close_fn()
                except Exception:
                    pass
        self._started = False
        print("[LibSignalSimulation] 仿真已关闭")

    @property
    def current_time(self) -> float:
        if not self.world:
            return 0.0
        try:
            if self.config['command']['world'] == 'cityflow':
                return float(self.world.eng.get_current_time())
            return float(self.world.eng.simulation.getTime())
        except Exception:
            return 0.0

    @property
    def vehiclegen(self):
        return self._vehiclegen

    @property
    def signal_complete(self) -> bool:
        return self._signal_complete

    @signal_complete.setter
    def signal_complete(self, value: bool):
        self._signal_complete = value


class LibSignalSolver(StandardSolver):
    """
    LibSignal 算法求解器适配器。
    """

    def __init__(self, args: StandardArgs):
        self.std_args = args
        self.agents = None
        self._interface = None

    def set_interface(self, interface):
        self._interface = interface
        if hasattr(interface, 'sim') and hasattr(interface.sim, 'agents'):
            self.agents = interface.sim.agents

    def get_action(self, state: Any) -> Any:
        if not self.agents:
            return None
        actions = []
        for agent in self.agents:
            ob = agent.get_ob()
            phase = agent.get_phase()
            action = agent.get_action(ob, phase, test=True)
            if np.isscalar(action):
                actions.append(int(action))
            else:
                actions.extend(np.asarray(action).reshape(-1).tolist())
        return actions

    def reset(self):
        if not self.agents:
            return
        for agent in self.agents:
            if hasattr(agent, 'reset'):
                agent.reset()


class LibSignalInterface(StandardInterface):
    """
    LibSignal Dashboard 接口适配器。
    """

    def __init__(self, sim: LibSignalSimulation, sys: LibSignalSolver, junction_manager, step_delay: float = 0.0):
        self.sim = sim
        self.sys = sys
        self.junction_manager = junction_manager
        self.step_delay = step_delay

        self._subscription_cache = {
            'lane_data': {},
            'traffic_light_data': {},
            'vehicle_data': {},
        }
        self._cached_netdata = None
        self._last_actions = None
        self._last_action_pairs = None
        self._action_interval = (
            sim.config['trainer'].get('action_interval', 10) if sim.config and 'trainer' in sim.config else 10
        )

        sys.set_interface(self)
        print(f"[LibSignalInterface] 初始化完成: action_interval={self._action_interval}")

    def _collect_actions(self):
        if not self.sim.agents:
            return []

        actions = []
        for agent in self.sim.agents:
            ob = agent.get_ob()
            phase = agent.get_phase()
            agent_actions = agent.get_action(ob, phase, test=True)
            if np.isscalar(agent_actions):
                actions.append(int(agent_actions))
            else:
                actions.extend(np.asarray(agent_actions).reshape(-1).astype(int).tolist())
        return actions

    def _collect_action_pairs(self):
        """Return SUMO actions paired with each agent's bound intersection.

        Per-intersection agents are not guaranteed to have the same order as
        ``world.intersections``.  Preserve the agent/intersection binding so a
        MaxPressure decision cannot be written to a different traffic light.
        Multi-intersection agents continue to fall back to world order.
        """
        if not self.sim.agents:
            return []

        pairs = []
        world_intersections = list(getattr(self.sim.world, 'intersections', []) or [])
        world_offset = 0

        for agent in self.sim.agents:
            ob = agent.get_ob()
            phase = agent.get_phase()
            agent_actions = agent.get_action(ob, phase, test=True)
            if np.isscalar(agent_actions):
                actions = [int(agent_actions)]
            else:
                actions = np.asarray(agent_actions).reshape(-1).astype(int).tolist()

            if len(actions) == 1 and getattr(agent, 'sub_agents', 1) == 1 and hasattr(agent, 'inter_obj'):
                pairs.append((agent.inter_obj, actions[0]))
                world_offset += 1
                continue

            targets = world_intersections[world_offset:world_offset + len(actions)]
            for inter, action in zip(targets, actions):
                pairs.append((inter, int(action)))
            world_offset += len(actions)

        return pairs

    def signal_update(self):
        self.sim.signal_complete = False
        try:
            self.update_subscription_cache()

            should_make_decision = (self.sim.step_count % self._action_interval == 0)
            if should_make_decision:
                if self.sim.config['command']['world'] == 'cityflow':
                    all_actions = self._collect_actions()
                    self._last_actions = all_actions
                    action_pairs = []
                else:
                    action_pairs = self._collect_action_pairs()
                    self._last_action_pairs = action_pairs
                    all_actions = [action for _, action in action_pairs]
            else:
                if self.sim.config['command']['world'] == 'cityflow':
                    all_actions = self._last_actions if self._last_actions is not None else []
                    action_pairs = []
                else:
                    action_pairs = self._last_action_pairs if self._last_action_pairs is not None else []
                    all_actions = [action for _, action in action_pairs]

            world_name = self.sim.config['command']['world']
            if all_actions:
                if world_name == 'cityflow':
                    self.sim._pending_actions = all_actions[:len(self.sim.world.intersections)]
                else:
                    for inter, action in action_pairs:
                        if inter is not None:
                            inter.pseudo_step(int(action))

            self.sim.signal_complete = True
        except Exception:
            self.sim.signal_complete = True
            raise

    def get_netdata(self) -> Dict[str, Any]:
        if not self.sim.world:
            return {}
        if self._cached_netdata is not None:
            return self._cached_netdata

        world_name = self.sim.config['command']['world']
        network_name = self.sim.config['command']['network']
        netdata = load_network_from_runtime(network_name, RUNTIME_ROOT, world=world_name)

        for intersection in self.sim.world.intersections:
            if intersection.id in netdata.get('inter', {}):
                netdata['inter'][intersection.id]['phases'] = list(getattr(intersection, 'phases', []))

        self._cached_netdata = netdata
        return netdata

    @property
    def subscription_cache(self) -> Dict[str, Any]:
        return self._subscription_cache

    def _get_sumo_lane_occupancy(self, eng, lane_id, vehicle_count, waiting_count):
        try:
            return float(eng.lane.getLastStepOccupancy(lane_id))
        except Exception:
            if vehicle_count <= 0:
                return 0.0
            return min(float(waiting_count) / max(vehicle_count, 1) * 100.0, 100.0)

    def _build_lane_cache_sumo(self):
        eng = self.sim.world.eng
        lane_counts = self.sim.world.get_lane_vehicle_count()
        waiting_counts = self.sim.world.get_lane_waiting_vehicle_count()

        lane_data = {}
        for lane_id, vehicle_count in lane_counts.items():
            waiting_count = waiting_counts.get(lane_id, 0)
            mean_speed = eng.lane.getLastStepMeanSpeed(lane_id) if vehicle_count > 0 else 0.0
            lane_data[lane_id] = {
                'vehicle_number': vehicle_count,
                'mean_speed': mean_speed,
                'occupancy': self._get_sumo_lane_occupancy(eng, lane_id, vehicle_count, waiting_count),
                'halting_number': waiting_count,
            }
        return lane_data

    def _build_lane_cache_cityflow(self):
        eng = self.sim.world.eng
        lane_counts = eng.get_lane_vehicle_count()
        waiting_counts = eng.get_lane_waiting_vehicle_count()
        lane_vehicles = eng.get_lane_vehicles()
        vehicle_speeds = eng.get_vehicle_speed()

        lane_data = {}
        for lane_id, vehicle_count in lane_counts.items():
            waiting_count = waiting_counts.get(lane_id, 0)
            vehicles = lane_vehicles.get(lane_id, [])
            if vehicles:
                mean_speed = sum(vehicle_speeds.get(vehicle_id, 0.0) for vehicle_id in vehicles) / len(vehicles)
            else:
                mean_speed = 0.0
            lane_data[lane_id] = {
                'vehicle_number': vehicle_count,
                'mean_speed': mean_speed,
                'occupancy': min(waiting_count / max(vehicle_count, 1) * 100.0, 100.0) if vehicle_count else 0.0,
                'halting_number': waiting_count,
            }
        return lane_data

    def _build_tl_cache_sumo(self):
        eng = self.sim.world.eng
        tl_data = {}
        step_length = self.sim.world.step_length
        for intersection in self.sim.world.intersections:
            current_phase_idx = intersection.current_phase
            phase_state = eng.trafficlight.getRedYellowGreenState(intersection.id)
            phase_duration_seconds = intersection.current_phase_time * step_length
            steps_until_next_decision = self._action_interval - (self.sim.step_count % self._action_interval)
            if intersection.current_phase_time < intersection.yellow_phase_time:
                steps_until_can_switch = intersection.yellow_phase_time - intersection.current_phase_time
            else:
                steps_until_can_switch = steps_until_next_decision

            tl_data[intersection.id] = {
                'phase_state': phase_state,
                'phase_duration': float(phase_duration_seconds),
                'phase_index': current_phase_idx,
                'next_switch': float(steps_until_can_switch * step_length),
            }
        return tl_data

    def _build_cityflow_phase_state(self, intersection) -> str:
        light_count = max(1, len(getattr(intersection, 'startlanes', [])))
        if getattr(intersection, '_current_phase', None) in getattr(intersection, 'yellow_phase_id', []):
            return 'y' * light_count

        phase_index = getattr(intersection, 'current_phase', 0)
        available = getattr(intersection, 'phase_available_startlanes', [])
        active_count = len(available[phase_index]) if phase_index < len(available) else 0
        if active_count <= 0:
            return 'r' * light_count
        return 'G' * active_count + 'r' * max(0, light_count - active_count)

    def _build_tl_cache_cityflow(self):
        tl_data = {}
        interval = float(self.sim.config.get('world', {}).get('interval', 1.0))
        for intersection in self.sim.world.intersections:
            phase_duration = float(getattr(intersection, 'current_phase_time', 0.0))
            if getattr(intersection, '_current_phase', None) in getattr(intersection, 'yellow_phase_id', []):
                remaining = max(float(intersection.yellow_phase_time) - phase_duration, 0.0)
            else:
                steps_until_next_decision = self._action_interval - (self.sim.step_count % self._action_interval)
                remaining = float(steps_until_next_decision * interval)

            tl_data[intersection.id] = {
                'phase_state': self._build_cityflow_phase_state(intersection),
                'phase_duration': phase_duration,
                'phase_index': getattr(intersection, 'current_phase', 0),
                'next_switch': remaining,
            }
        return tl_data

    def update_subscription_cache(self):
        if not self.sim.world:
            return

        world_name = self.sim.config['command']['world']
        if world_name == 'cityflow':
            lane_data = self._build_lane_cache_cityflow()
            tl_data = self._build_tl_cache_cityflow()
        else:
            lane_data = self._build_lane_cache_sumo()
            tl_data = self._build_tl_cache_sumo()

        self._subscription_cache['lane_data'] = lane_data
        self._subscription_cache['traffic_light_data'] = tl_data
