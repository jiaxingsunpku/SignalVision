"""
Dashboard专用接口

作为SUMO系统和Dashboard JunctionAgent之间的桥梁：
1. 包装原有的IF接口
2. 添加步骤延迟控制
3. 在每个仿真步骤后更新JunctionAgent
4. 不修改原有的SUMO和智能体系统
"""

import time
from interface.IF import IF


class DashboardInterface(IF):
    """
    Dashboard专用接口，继承自IF并添加Dashboard特定功能
    """
    
    def __init__(self, sim, sys, junction_manager=None, step_delay=0):
        """
        初始化Dashboard接口
        
        Args:
            sim: SUMO仿真实例
            sys: 智能体系统实例
            junction_manager: JunctionManager实例（用于更新前端数据）
            step_delay: 步骤延迟（毫秒）
        """
        # 调用父类初始化
        super().__init__(sim, sys)
        
        # Dashboard特定属性
        self.junction_manager = junction_manager
        self.step_delay = step_delay / 1000.0 if step_delay > 0 else 0  # 转换为秒
    
    def signal_update(self):
        """
        重写signal_update，在智能体决策后添加延迟并更新JunctionAgent
        """
        # 1. 调用父类方法执行智能体决策
        super().signal_update()
        
        # 2. 更新JunctionAgent数据（如果设置了）
        if self.junction_manager:
            self._update_junction_agents()
        
        # 3. 添加步骤延迟（如果设置了）
        if self.step_delay > 0:
            time.sleep(self.step_delay)
    
    def _update_junction_agents(self):
        """从订阅缓存更新JunctionAgent数据"""
        if not self.junction_manager:
            return
        
        subscription_cache = self.subscription_cache
        
        # 1. 更新车道数据
        lane_data = subscription_cache.get('lane_data', {})
        for lane_id, data in lane_data.items():
            # 查找该车道属于哪个路口
            junction_id = self._find_junction_for_lane(lane_id)
            if junction_id:
                junction = self.junction_manager.get_junction(junction_id)
                if junction:
                    import traci
                    
                    # 获取车道数据
                    vehicle_count = data.get(traci.constants.LAST_STEP_VEHICLE_NUMBER, 0)
                    mean_speed = data.get(traci.constants.LAST_STEP_MEAN_SPEED, 0.0)
                    halting_count = data.get(traci.constants.LAST_STEP_VEHICLE_HALTING_NUMBER, 0)
                    
                    # 计算占有率：occupied_length / lane_length * 100
                    occupied_length = data.get(traci.constants.LAST_STEP_LENGTH, 0.0)
                    lane_length = self._get_lane_length(lane_id)
                    occupancy = (occupied_length / lane_length * 100) if lane_length > 0 else 0.0
                    
                    junction.update_lane_data(
                        lane_id=lane_id,
                        vehicle_count=vehicle_count,
                        mean_speed=mean_speed,
                        occupancy=occupancy,
                        halting_count=halting_count
                    )
        
        # 2. 更新交通信号灯数据
        tl_data = subscription_cache.get('traffic_light_data', {})
        for tl_id, data in tl_data.items():
            junction = self.junction_manager.get_junction(tl_id)
            if junction and junction.traffic_light_state:
                import traci
                junction.update_traffic_light(
                    phase_state=data.get(traci.constants.TL_RED_YELLOW_GREEN_STATE, ''),
                    phase_duration=data.get(traci.constants.TL_PHASE_DURATION, 0.0),
                    next_switch_time=data.get(traci.constants.TL_NEXT_SWITCH, 0.0)
                )
        
        # 3. 计算所有路口的指标
        self.junction_manager.update_all_metrics()
    
    def _find_junction_for_lane(self, lane_id):
        """根据lane_id查找对应的junction_id"""
        if not hasattr(self.sim, 'netdata') or 'inter' not in self.sim.netdata:
            return None
        
        for junction_id, junction_info in self.sim.netdata['inter'].items():
            incoming_lanes = junction_info.get('incoming_lanes', [])
            outgoing_lanes = junction_info.get('outgoing_lanes', [])
            
            if lane_id in incoming_lanes or lane_id in outgoing_lanes:
                return junction_id
        
        return None
    
    def _get_lane_length(self, lane_id):
        """获取车道长度"""
        if hasattr(self.sim, 'netdata') and 'lane' in self.sim.netdata:
            lane_info = self.sim.netdata['lane'].get(lane_id, {})
            return lane_info.get('length', 100.0)  # 默认100米
        return 100.0
    
    def set_junction_manager(self, junction_manager):
        """设置JunctionManager实例"""
        self.junction_manager = junction_manager
    
    def set_step_delay(self, step_delay):
        """动态设置步骤延迟（毫秒）"""
        self.step_delay = step_delay / 1000.0 if step_delay > 0 else 0

