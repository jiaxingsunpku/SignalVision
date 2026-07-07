"""
路口逻辑智能体 (Junction Agent)

这是一个独立的中间层，用于管理每个路口的状态、监控和交互逻辑。
与SUMO仿真和强化学习智能体系统完全解耦。
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class LaneInfo:
    """车道信息"""
    lane_id: str
    direction: str  # 'incoming' or 'outgoing'
    length: float = 0.0
    speed_limit: float = 0.0
    # 实时数据（从外部更新）
    vehicle_count: int = 0
    mean_speed: float = 0.0
    occupancy: float = 0.0
    halting_count: int = 0


@dataclass
class TrafficLightState:
    """
    交通信号灯状态
    
    Attributes:
        phase_state: 信号灯状态字符串（如 "GGGGrrrrGGGGrrrr"）
        phase_duration: 当前相位已持续时间（秒）
        next_switch_time: 距离下次可能切换的时间（秒）
        last_update_time: 最后更新时间戳
    """
    phase_state: str = ""
    phase_duration: float = 0.0
    next_switch_time: float = 0.0
    last_update_time: float = field(default_factory=time.time)


@dataclass
class JunctionMetrics:
    """路口性能指标"""
    # 实时指标
    total_vehicles: int = 0
    average_speed: float = 0.0
    average_occupancy: float = 0.0
    total_halting: int = 0
    
    # 统计指标（累计）
    total_vehicles_passed: int = 0
    total_waiting_time: float = 0.0
    max_queue_length: int = 0
    
    # 拥堵级别 (0-1)
    congestion_level: float = 0.0
    
    last_update_time: float = field(default_factory=time.time)


class JunctionAgent:
    """
    路口逻辑智能体
    
    职责：
    1. 维护路口的静态信息（位置、车道、连接等）
    2. 接收和存储实时交通状态
    3. 计算路口性能指标
    4. 提供查询接口供前端显示
    5. 支持未来的交互功能（手动控制、优先级调整等）
    
    设计原则：
    - 完全独立，不依赖SUMO或RL智能体
    - 数据驱动，通过update方法接收外部数据
    - 线程安全（未来可能需要）
    """
    
    def __init__(self, junction_id: str, position: tuple, junction_type: str = "traffic_light"):
        """
        初始化路口智能体
        
        Args:
            junction_id: 路口唯一标识
            position: 路口坐标 (x, y)
            junction_type: 路口类型 ("traffic_light", "priority", "right_before_left")
        """
        self.junction_id = junction_id
        self.position = position
        self.junction_type = junction_type
        
        # 静态数据
        self.incoming_lanes: Dict[str, LaneInfo] = {}
        self.outgoing_lanes: Dict[str, LaneInfo] = {}
        self.connected_junctions: List[str] = []
        
        # 动态数据
        self.traffic_light_state = TrafficLightState() if junction_type == "traffic_light" else None
        self.metrics = JunctionMetrics()
        
        # 历史数据（保留最近N个时间步）
        self.history_size = 100
        self.metrics_history: List[JunctionMetrics] = []
        
        # 控制模式
        self.control_mode = "auto"  # "auto", "manual", "priority"
        self.manual_phase: Optional[str] = None
        
        # 状态标志
        self.is_active = True
        self.last_update_time = time.time()
        
    def add_lane(self, lane_id: str, direction: str, length: float = 0.0, speed_limit: float = 0.0):
        """添加车道信息"""
        lane_info = LaneInfo(
            lane_id=lane_id,
            direction=direction,
            length=length,
            speed_limit=speed_limit
        )
        
        if direction == "incoming":
            self.incoming_lanes[lane_id] = lane_info
        elif direction == "outgoing":
            self.outgoing_lanes[lane_id] = lane_info
        else:
            raise ValueError(f"Invalid direction: {direction}")
    
    def add_connected_junction(self, junction_id: str):
        """添加相邻路口"""
        if junction_id not in self.connected_junctions:
            self.connected_junctions.append(junction_id)
    
    def update_lane_data(self, lane_id: str, vehicle_count: int, mean_speed: float, 
                         occupancy: float, halting_count: int):
        """更新车道实时数据"""
        # 查找车道
        lane_info = None
        if lane_id in self.incoming_lanes:
            lane_info = self.incoming_lanes[lane_id]
        elif lane_id in self.outgoing_lanes:
            lane_info = self.outgoing_lanes[lane_id]
        
        if lane_info:
            lane_info.vehicle_count = vehicle_count
            lane_info.mean_speed = mean_speed
            lane_info.occupancy = occupancy
            lane_info.halting_count = halting_count
            
    def update_traffic_light(self, phase_state: str, phase_duration: float, 
                            next_switch_time: float):
        """
        更新交通信号灯状态
        
        Args:
            phase_state: 信号灯状态字符串（如 "GGGGrrrrGGGGrrrr"）
            phase_duration: 当前相位已持续时间（秒）
            next_switch_time: 距离下次可能切换的时间（秒）
        """
        if self.traffic_light_state:
            self.traffic_light_state.phase_state = phase_state
            self.traffic_light_state.phase_duration = phase_duration
            self.traffic_light_state.next_switch_time = next_switch_time
            self.traffic_light_state.last_update_time = time.time()
    
    def calculate_metrics(self):
        """计算路口性能指标"""
        total_vehicles = 0
        total_speed = 0
        total_occupancy = 0
        total_halting = 0
        max_queue_length = 0
        lane_count = 0
        
        # 只统计入向车道
        for lane_info in self.incoming_lanes.values():
            total_vehicles += lane_info.vehicle_count
            total_speed += lane_info.mean_speed * lane_info.vehicle_count if lane_info.vehicle_count > 0 else 0
            total_occupancy += lane_info.occupancy
            total_halting += lane_info.halting_count
            max_queue_length = max(max_queue_length, lane_info.halting_count)
            lane_count += 1
        
        # 更新指标
        self.metrics.total_vehicles = total_vehicles
        self.metrics.average_speed = total_speed / total_vehicles if total_vehicles > 0 else 0
        self.metrics.average_occupancy = total_occupancy / lane_count if lane_count > 0 else 0
        self.metrics.total_halting = total_halting
        self.metrics.max_queue_length = max_queue_length
        
        # 计算拥堵级别（优化算法：车辆数 + 速度）
        if total_vehicles < 5:
            # 车辆少于5辆，一律视为顺畅
            self.metrics.congestion_level = 0.0
        else:
            # 车辆数 >= 5，根据速度判断拥堵
            # 假设道路限速为13.89 m/s (50 km/h)
            speed_limit = 13.89
            
            # 速度因子：速度越低拥堵越严重
            if self.metrics.average_speed > 0:
                speed_factor = 1.0 - min(self.metrics.average_speed / speed_limit, 1.0)
            else:
                speed_factor = 1.0  # 速度为0，完全拥堵
            
            # 车辆数因子：车辆越多拥堵越严重
            vehicle_factor = min(total_vehicles / (lane_count * 15), 1.0)  # 假设每车道15辆车为饱和
            
            # 停车因子
            halting_factor = min(total_halting / (lane_count * 8), 1.0)  # 假设每车道8辆车排队为饱和
            
            # 综合拥堵度：速度50%，车辆数25%，停车25%
            self.metrics.congestion_level = (speed_factor * 0.5 + vehicle_factor * 0.25 + halting_factor * 0.25)
        
            # 调试输出（仅在有车辆时）
            if hasattr(self, '_debug_counter'):
                self._debug_counter = (self._debug_counter + 1) % 100
            else:
                self._debug_counter = 0
            
            if self._debug_counter == 0:  # 每100次输出一次
                print(f"[Junction {self.junction_id}] 车辆={total_vehicles}, 拥堵度={self.metrics.congestion_level:.2f}")
        
        self.metrics.last_update_time = time.time()
        
        # 保存到历史
        if len(self.metrics_history) >= self.history_size:
            self.metrics_history.pop(0)
        self.metrics_history.append(JunctionMetrics(**vars(self.metrics)))
        
        self.last_update_time = time.time()

    def _serialize_metrics_sample(self, metrics: JunctionMetrics, sample_index: int) -> Dict[str, Any]:
        """将历史指标样本转换为前端可直接绘图的数据。"""
        return {
            "sample_index": sample_index,
            "timestamp": metrics.last_update_time,
            "total_vehicles": metrics.total_vehicles,
            "average_speed": round(metrics.average_speed, 2),
            "average_occupancy": round(metrics.average_occupancy, 2),
            "total_halting": metrics.total_halting,
            "congestion_level": round(metrics.congestion_level, 3),
            "total_vehicles_passed": metrics.total_vehicles_passed,
            "total_waiting_time": round(metrics.total_waiting_time, 2),
            "max_queue_length": metrics.max_queue_length
        }

    def _serialize_metrics_history(self) -> List[Dict[str, Any]]:
        """获取固定窗口内的路口历史指标。"""
        return [
            self._serialize_metrics_sample(metrics, index)
            for index, metrics in enumerate(self.metrics_history)
        ]
    
    def get_state_dict(self) -> Dict[str, Any]:
        """获取路口完整状态（供API返回）"""
        return {
            "junction_id": self.junction_id,
            "position": self.position,
            "junction_type": self.junction_type,
            "is_active": self.is_active,
            "control_mode": self.control_mode,
            "last_update_time": self.last_update_time,
            
            # 车道信息
            "incoming_lanes": {
                lane_id: {
                    "lane_id": lane.lane_id,
                    "length": lane.length,
                    "speed_limit": lane.speed_limit,
                    "vehicle_count": lane.vehicle_count,
                    "mean_speed": lane.mean_speed,
                    "occupancy": lane.occupancy,
                    "halting_count": lane.halting_count
                }
                for lane_id, lane in self.incoming_lanes.items()
            },
            "outgoing_lanes": {
                lane_id: {
                    "lane_id": lane.lane_id,
                    "length": lane.length,
                    "speed_limit": lane.speed_limit,
                    "vehicle_count": lane.vehicle_count,
                    "mean_speed": lane.mean_speed,
                    "occupancy": lane.occupancy,
                    "halting_count": lane.halting_count
                }
                for lane_id, lane in self.outgoing_lanes.items()
            },
            
            # 信号灯状态
            "traffic_light": {
                "phase_state": self.traffic_light_state.phase_state,
                "phase_duration": self.traffic_light_state.phase_duration,
                "next_switch_time": self.traffic_light_state.next_switch_time,
                "last_update_time": self.traffic_light_state.last_update_time
            } if self.traffic_light_state else None,
            
            # 性能指标
            "metrics": {
                "total_vehicles": self.metrics.total_vehicles,
                "average_speed": round(self.metrics.average_speed, 2),
                "average_occupancy": round(self.metrics.average_occupancy, 2),
                "total_halting": self.metrics.total_halting,
                "congestion_level": round(self.metrics.congestion_level, 3),
                "total_vehicles_passed": self.metrics.total_vehicles_passed,
                "total_waiting_time": round(self.metrics.total_waiting_time, 2),
                "max_queue_length": self.metrics.max_queue_length,
                "last_update_time": self.metrics.last_update_time
            },
            "metrics_history": self._serialize_metrics_history(),
            
            # 连接信息
            "connected_junctions": self.connected_junctions
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """获取路口摘要信息（供地图显示）"""
        return {
            "junction_id": self.junction_id,
            "position": self.position,
            "junction_type": self.junction_type,
            "is_active": self.is_active,
            "congestion_level": round(self.metrics.congestion_level, 2),
            "total_vehicles": self.metrics.total_vehicles,
            "total_halting": self.metrics.total_halting
        }
    
    def set_control_mode(self, mode: str, manual_phase: Optional[str] = None):
        """设置控制模式"""
        if mode not in ["auto", "manual", "priority"]:
            raise ValueError(f"Invalid control mode: {mode}")
        
        self.control_mode = mode
        self.manual_phase = manual_phase
    
    def reset(self):
        """重置路口状态"""
        # 重置动态数据
        for lane in self.incoming_lanes.values():
            lane.vehicle_count = 0
            lane.mean_speed = 0.0
            lane.occupancy = 0.0
            lane.halting_count = 0
        
        for lane in self.outgoing_lanes.values():
            lane.vehicle_count = 0
            lane.mean_speed = 0.0
            lane.occupancy = 0.0
            lane.halting_count = 0
        
        # 重置指标
        self.metrics = JunctionMetrics()
        self.metrics_history.clear()
        
        # 重置信号灯
        if self.traffic_light_state:
            self.traffic_light_state = TrafficLightState()
        
        self.last_update_time = time.time()


class JunctionManager:
    """
    路口管理器
    
    管理所有路口智能体，提供统一的访问接口
    """
    
    def __init__(self):
        self.junctions: Dict[str, JunctionAgent] = {}
        self.network_data: Optional[Dict] = None
    
    def initialize_from_network_data(self, network_data: Dict):
        """从网络数据初始化所有路口智能体"""
        self.network_data = network_data
        self.junctions.clear()  # 换图即清空旧路口，避免多次 load-map 累积（否则切回旧图 junction_count 不回落）

        # 从inter数据创建路口智能体
        if "inter" in network_data:
            for junction_id, junction_info in network_data["inter"].items():
                position = (junction_info.get("x", 0), junction_info.get("y", 0))
                junction_type = "traffic_light" if junction_info.get("have_tl", False) else "priority"
                
                agent = JunctionAgent(junction_id, position, junction_type)
                
                # 添加车道
                for lane_id in junction_info.get("incoming_lanes", []):
                    lane_data = self._get_lane_data(lane_id, network_data)
                    agent.add_lane(
                        lane_id=lane_id,
                        direction="incoming",
                        length=lane_data.get("length", 0.0),
                        speed_limit=lane_data.get("speed", 0.0)
                    )
                
                for lane_id in junction_info.get("outgoing_lanes", []):
                    lane_data = self._get_lane_data(lane_id, network_data)
                    agent.add_lane(
                        lane_id=lane_id,
                        direction="outgoing",
                        length=lane_data.get("length", 0.0),
                        speed_limit=lane_data.get("speed", 0.0)
                    )
                
                self.junctions[junction_id] = agent
        
        print(f"[JunctionManager] 初始化完成，共创建 {len(self.junctions)} 个路口智能体")
    
    def _get_lane_data(self, lane_id: str, network_data: Dict) -> Dict:
        """从网络数据中获取车道信息"""
        if "lane" in network_data and lane_id in network_data["lane"]:
            return network_data["lane"][lane_id]
        return {}
    
    def get_junction(self, junction_id: str) -> Optional[JunctionAgent]:
        """获取指定路口智能体"""
        return self.junctions.get(junction_id)
    
    def get_all_junctions(self) -> Dict[str, JunctionAgent]:
        """获取所有路口智能体"""
        return self.junctions
    
    def get_all_summaries(self) -> List[Dict[str, Any]]:
        """获取所有路口的摘要信息"""
        return [agent.get_summary() for agent in self.junctions.values()]
    
    def update_all_metrics(self):
        """更新所有路口的性能指标"""
        for agent in self.junctions.values():
            agent.calculate_metrics()
    
    def reset_all(self):
        """重置所有路口"""
        for agent in self.junctions.values():
            agent.reset()
