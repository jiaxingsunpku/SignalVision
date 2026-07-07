from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import BaseAgent
from common.registry import Registry
from generator import LaneVehicleGenerator, IntersectionPhaseGenerator, IntersectionVehicleGenerator
import numpy as np
import gym

@Registry.register_model('fixedtime')
class FixedTimeAgent(BaseAgent):
    '''
    FixedTimeAgent gives a predefined time duration and phase order.
    '''
    def __init__(self, world, rank):
        super().__init__(world)
        self.world = world
        self.rank = rank
        self.model = None

        # get generator for each MaxPressure
        inter_id = self.world.intersection_ids[self.rank]
        self.inter_obj = self.world.id2intersection[inter_id]
        self.ob_generator = self.ob_generator = LaneVehicleGenerator(self.world, self.inter_obj, ['lane_count'], in_only=True, average=None)
        self.phase_generator = IntersectionPhaseGenerator(world, self.inter_obj, ["phase"],
                                                          targets=["cur_phase"], negative=False)
        self.reward_generator = LaneVehicleGenerator(self.world, self.inter_obj, ["lane_count"],
                                                     in_only=True, average='all', negative=True)
        
        self.queue = LaneVehicleGenerator(self.world, self.inter_obj,
                                                     ["lane_waiting_count"], in_only=True,
                                                     negative=False)

        self.delay = LaneVehicleGenerator(self.world, self.inter_obj,
                                                     ["lane_delay"], in_only=True,
                                                     negative=False) 

        self.action_space = gym.spaces.Discrete(len(self.inter_obj.phases))
        # dirrerent datasets have the same t_fixed
        self.t_fixed = Registry.mapping['model_mapping']['setting'].param['t_fixed']

        # 真实配时：从 JSON 读取每个相位的实际绿灯时长
        self._lookup = None
        self._start_sod: int = 0  # 仿真 t=0 对应的一天中第几秒
        model_param = Registry.mapping['model_mapping']['setting'].param
        rt_cfg = model_param.get('real_timing')
        if rt_cfg:
            json_path = rt_cfg.get(
                'json_path',
                'utils/sumo_signal_reference_ezhou_vehicle_compact.json',
            )
            self._start_sod = int(rt_cfg.get('start_second_of_day', 0))
            abs_json = Path(__file__).parent.parent / json_path
            try:
                from utils.phase_lookup import PhaseLookup
                self._lookup = PhaseLookup(abs_json)
                print(f"[FixedTimeAgent] 已加载真实配时 JSON: {abs_json}")
            except Exception as exc:
                print(f"[FixedTimeAgent] 无法加载真实配时 JSON ({exc})，退回 t_fixed={self.t_fixed}")

    def __repr__(self):
        return 'FixedTime Agent has no Network model'
        
    def reset(self):
        '''
        reset
        Reset information, including ob_generator, phase_generator, queue, delay, etc.

        :param: None
        :return: None
        '''
        inter_id = self.world.intersection_ids[self.rank]
        self.inter_obj = self.world.id2intersection[inter_id]
        self.ob_generator = self.ob_generator = LaneVehicleGenerator(self.world, self.inter_obj, ['lane_count'], in_only=True, average=None)
        self.phase_generator = IntersectionPhaseGenerator(self.world, self.inter_obj, ["phase"],
                                                          targets=["cur_phase"], negative=False)
        self.reward_generator = LaneVehicleGenerator(self.world, self.inter_obj, ["lane_count"],
                                                     in_only=True, average='all', negative=True)
        
        self.queue = LaneVehicleGenerator(self.world, self.inter_obj,
                                                     ["lane_waiting_count"], in_only=True,
                                                     negative=False)

        self.delay = LaneVehicleGenerator(self.world, self.inter_obj,
                                                     ["lane_delay"], in_only=True,
                                                     negative=False)

    def _get_phase_duration(self, inter_id: str, phase_idx: int) -> int:
        """返回该路口当前相位的实际绿灯时长（秒）。
        
        若路口不在 JSON 中，或当前时段不可用，则回退到 t_fixed。
        """
        if self._lookup is None:
            return self.t_fixed
        sim_time = int(self.world.get_current_time())
        sod = (self._start_sod + sim_time) % 86400
        try:
            _, period, _, _ = self._lookup._get_period(inter_id, sod)
            if not period['available']:
                return self.t_fixed
            stages = period['stages']
            idx = phase_idx % len(stages)
            return max(1, int(stages[idx][1]))
        except Exception:
            return self.t_fixed

    def get_ob(self):
        '''
        get_ob
        Get observation from environment.

        :param: None
        :return x_obs: observation generated by ob_generator
        '''
        x_obs = []
        x_obs.append(self.ob_generator.generate())
        x_obs = np.array(x_obs, dtype=np.float32)
        return x_obs

    def get_reward(self):
        '''
        get_reward
        Get reward from environment.

        :param: None
        :return rewards: rewards generated by reward_generator
        '''
        rewards = []
        rewards.append(self.reward_generator.generate())
        rewards = np.squeeze(np.array(rewards)) * 12
        return rewards
    
    def get_phase(self):
        '''
        get_phase
        Get current phase of intersection(s) from environment.

        :param: None
        :return phase: current phase generated by phase_generator
        '''
        phase = []
        phase.append(self.phase_generator.generate())
        # phase = np.concatenate(phase, dtype=np.int8)
        phase = (np.concatenate(phase)).astype(np.int8)
        return phase
    
    def get_action(self, ob, phase, test=True):
        '''
        get_action
        Generate action.

        :param ob: observation
        :param phase: current phase
        :param test: boolean, decide whether is test process
        :return action: action in the next order
        '''
        # phases: just index of self.inter_obj.phases, not green light index
        assert self.inter_obj.current_phase == phase[-1]
        inter_id = self.world.intersection_ids[self.rank]
        duration = self._get_phase_duration(inter_id, self.inter_obj.current_phase)
        if self.inter_obj.current_phase_time < duration:
            return self.inter_obj.current_phase
        else:
            return (self.inter_obj.current_phase + 1) % len(self.inter_obj.phases)

    def get_queue(self):
        '''
        get_queue
        Get queue length of intersection.

        :param: None
        :return: total queue length
        '''
        queue = []
        queue.append(self.queue.generate())
        queue = np.sum(np.squeeze(np.array(queue)))
        return queue

    def get_delay(self):
        '''
        get_delay
        Get delay of intersection.

        :param: None
        :return: total delay
        '''
        delay = []
        delay.append(self.delay.generate())
        delay = np.sum(np.squeeze(np.array(delay)))
        return delay