"""
标准化仿真接口定义

这个文件定义了 Dashboard 期望的标准接口（抽象基类）。
任何训练系统的适配器都需要实现这些接口。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class StandardArgs:
    """标准化参数对象"""
    # 仿真基本参数
    sim: str = '81'                    # 场景名称
    tsc: str = 'maxpressure'          # 算法类型
    world: str = 'sumo'               # 仿真器类型
    dataset: str = 'onfly'            # LibSignal 数据集类型
    mode: str = 'test'                 # 运行模式
    nogui: bool = True                 # 是否无GUI
    
    # 仿真时间参数
    simlen: int = 3600                 # 仿真时长（秒）
    gmin: int = 1                      # 最小绿灯时间
    r: int = 3                         # 红灯间隔
    y: int = 2                         # 黄灯时长
    
    # 流量参数
    demand: str = 'fixed'              # 流量类型
    scale: float = 2.0                 # 流量倍率
    
    # 可视化参数
    enable_db: bool = False            # 是否启用数据库
    render_interval: int = 400         # 渲染间隔
    
    # Dashboard特定参数
    step_delay: float = 0.0            # 步骤延迟（秒）
    interface: str = 'libsumo'         # SUMO接口类型
    prefix: str = ''                   # LibSignal 输出目录前缀
    load_episode: Optional[int] = None # 推理时加载的epoch
    load_model: bool = True            # 是否加载模型
    test_model: bool = True            # 是否执行测试/推理
    train_model: bool = False          # 是否执行训练
    
    # 其他参数
    port: int = 8020                   # SUMO端口
    normalized_k: float = 0.5          # 归一化参数
    offset: float = 0.05               # 偏移量
    thread_num: int = 4                # 仿真线程数
    ngpu: str = '0'                    # GPU编号
    seed: Optional[int] = None         # 随机种子
    debug: bool = False                # 调试模式
    delay_type: str = 'apx'            # 延迟计算方式
    
    # 模型参数（用于PPO等）
    resume: bool = False               # 是否恢复训练
    resume_path: str = ''              # 恢复路径


class StandardSimulation(ABC):
    """
    标准化仿真接口
    
    任何训练系统的仿真模块都需要实现这个接口，
    以便 Dashboard 能够统一调用。
    """
    
    @abstractmethod
    def __init__(self, args: StandardArgs, nogui: bool = True):
        """
        初始化仿真
        
        Args:
            args: 标准化参数对象
            nogui: 是否无GUI模式
        """
        pass
    
    @abstractmethod
    def gen_sim(self):
        """生成仿真环境（初始化路网、车辆生成器等）"""
        pass
    
    @abstractmethod
    def start(self):
        """启动仿真"""
        pass
    
    @abstractmethod
    def sim_step(self):
        """执行一个仿真步骤"""
        pass
    
    @abstractmethod
    def update_netdata(self):
        """更新网络数据（路网拓扑、路口信息等）"""
        pass
    
    @abstractmethod
    def update_travel_times(self):
        """更新通行时间统计"""
        pass
    
    @abstractmethod
    def set_interface(self, interface):
        """设置Dashboard接口"""
        pass
    
    @abstractmethod
    def close(self):
        """关闭仿真"""
        pass
    
    @property
    @abstractmethod
    def current_time(self) -> float:
        """当前仿真时间"""
        pass
    
    @property
    @abstractmethod
    def vehiclegen(self):
        """车辆生成器对象"""
        pass
    
    @property
    @abstractmethod
    def signal_complete(self) -> bool:
        """信号更新是否完成"""
        pass
    
    @signal_complete.setter
    @abstractmethod
    def signal_complete(self, value: bool):
        """设置信号更新完成标志"""
        pass


class StandardSolver(ABC):
    """
    标准化算法求解器接口
    
    所有交通信号控制算法（PPO、MaxPressure、FixedTime等）
    都需要实现这个接口。
    """
    
    @abstractmethod
    def __init__(self, args: StandardArgs):
        """
        初始化算法求解器
        
        Args:
            args: 标准化参数对象
        """
        pass
    
    @abstractmethod
    def set_interface(self, interface):
        """设置Dashboard接口"""
        pass
    
    @abstractmethod
    def get_action(self, state: Any) -> Any:
        """
        获取动作（信号控制决策）
        
        Args:
            state: 当前状态
            
        Returns:
            action: 控制动作
        """
        pass
    
    @abstractmethod
    def reset(self):
        """重置算法状态"""
        pass


class StandardInterface(ABC):
    """
    标准化Dashboard接口
    
    连接仿真系统和算法系统的桥梁，负责数据流转和控制协调。
    """
    
    @abstractmethod
    def __init__(self, sim: StandardSimulation, sys: StandardSolver, 
                 junction_manager, step_delay: float = 0.0):
        """
        初始化接口
        
        Args:
            sim: 仿真对象
            sys: 算法对象
            junction_manager: 路口管理器
            step_delay: 步骤延迟
        """
        pass
    
    @abstractmethod
    def signal_update(self):
        """信号更新（触发算法决策）"""
        pass
    
    @abstractmethod
    def get_netdata(self) -> Dict[str, Any]:
        """
        获取网络数据
        
        Returns:
            {
                'junctions': [...],      # 路口列表
                'lanes': {...},          # 车道信息
                'edges': {...},          # 道路信息
                'connections': {...},    # 连接关系
            }
        """
        pass
    
    @property
    @abstractmethod
    def subscription_cache(self) -> Dict[str, Any]:
        """
        订阅缓存
        
        Returns:
            {
                'lane_data': {...},          # 车道数据
                'traffic_light_data': {...}, # 信号灯数据
                'vehicle_data': {...},       # 车辆数据
            }
        """
        pass
    
    @abstractmethod
    def update_subscription_cache(self):
        """更新订阅缓存"""
        pass
