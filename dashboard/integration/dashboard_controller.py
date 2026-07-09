"""
Dashboard集成控制器

作为中间层，整合：
1. 训练系统（通过适配层）
2. 仿真系统（通过适配层）
3. JunctionAgent管理层
4. 前端通信接口

注意：现在使用适配层连接训练系统，不直接依赖具体实现
"""

import sys
import os
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 使用适配层接口
from adapter import (
    StandardArgs,
    StandardSimulation,
    StandardSolver,
    StandardInterface,
    LibSignalSimulation,
    LibSignalSolver,
    LibSignalInterface,
    ConfigConverter
)

from dashboard.integration.junction_agent import JunctionManager

class DashboardController:
    """
    Dashboard集成控制器
    
    职责：
    1. 初始化和管理仿真系统（通过适配层）
    2. 初始化和管理智能体系统（通过适配层）
    3. 初始化和管理JunctionAgent
    4. 协调数据流：仿真 → JunctionAgent → 前端
    5. 协调决策流：JunctionAgent → 智能体系统 → 仿真
    """
    
    def __init__(self, args_list: Optional[List[str]] = None, config: Optional[Dict[str, Any]] = None):
        """
        初始化Dashboard控制器
        
        Args:
            args_list: 命令行参数列表，如 ['-sim', '81', '-tsc', 'maxpressure', ...]
            config: 配置字典（如果提供，优先使用此配置而不是 args_list）
        """
        # 解析参数并转换为 StandardArgs
        if config:
            # 从配置字典创建 StandardArgs
            self.args = ConfigConverter.dashboard_config_to_standard(config)
        elif args_list:
            # 从命令行参数列表创建 StandardArgs
            self.args = self._parse_args_list(args_list)
        else:
            # 使用默认参数
            self.args = StandardArgs()
        
        # 强制设置为test模式（Dashboard不进行训练）
        self.args.mode = 'test'
        
        # 核心组件（使用标准接口）
        self.simulation: Optional[StandardSimulation] = None
        self.solver: Optional[StandardSolver] = None
        self.interface: Optional[StandardInterface] = None
        self.junction_manager = JunctionManager()
        
        # 状态标志
        self.is_initialized = False
        self.is_running = False
        self.current_step = 0
        
        # 仿真参数
        self.total_steps = self.args.simlen
        self.step_delay = self.args.step_delay
        
        print(f"[DashboardController] 初始化完成: 场景={self.args.sim}, 算法={self.args.tsc}, "
              f"GUI={'否' if self.args.nogui else '是'}, 数据库={'是' if self.args.enable_db else '否'}")
        print(f"[DashboardController] *** 延迟配置: step_delay={self.step_delay}s (类型: {type(self.step_delay)}) ***")
    
    def _parse_args_list(self, args_list: List[str]) -> StandardArgs:
        """
        从命令行参数列表创建 StandardArgs
        
        Args:
            args_list: 命令行参数列表，如 ['-sim', '81', '-tsc', 'maxpressure', ...]
            
        Returns:
            StandardArgs 对象
        """
        args_dict = {}
        i = 0
        while i < len(args_list):
            if args_list[i].startswith('-'):
                key = args_list[i].lstrip('-')
                if i + 1 < len(args_list) and not args_list[i + 1].startswith('-'):
                    value = args_list[i + 1]
                    # 类型转换
                    if value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    elif value.isdigit():
                        value = int(value)
                    elif value.replace('.', '', 1).isdigit():
                        value = float(value)
                    args_dict[key] = value
                    i += 2
                else:
                    args_dict[key] = True
                    i += 1
            else:
                i += 1
        
        # 创建 StandardArgs 并设置值
        std_args = StandardArgs()
        for key, value in args_dict.items():
            if hasattr(std_args, key):
                setattr(std_args, key, value)
        
        # 调试输出
        if 'step_delay' in args_dict:
            print(f"[_parse_args_list] step_delay 从命令行解析: {args_dict['step_delay']} (类型: {type(args_dict['step_delay'])})")
        print(f"[_parse_args_list] 最终 std_args.step_delay = {std_args.step_delay} (类型: {type(std_args.step_delay)})")
        
        return std_args
    
    def initialize(self):
        """初始化所有系统组件（使用适配层）"""
        if self.is_initialized:
            print("[DashboardController] 已经初始化，跳过")
            return
        
        print("[DashboardController] 开始初始化系统...")
        
        # 切换到项目根目录（确保相对路径正确）
        os.chdir(PROJECT_ROOT)
        
        try:
            # 1. 初始化仿真系统（使用 LibSignal 适配器）
            print(f"[DashboardController] 创建仿真系统: {self.args.sim}")
            self.simulation = LibSignalSimulation(args=self.args, nogui=self.args.nogui)
            
            # 2. 初始化智能体系统（使用 LibSignal 适配器）
            print(f"[DashboardController] 创建智能体系统: {self.args.tsc}")
            self.solver = LibSignalSolver(args=self.args)
            
            # 3. 生成仿真环境
            print("[DashboardController] 生成仿真环境...")
            self.simulation.gen_sim()
            
            # 4. 创建Dashboard专用接口并连接各组件
            print("[DashboardController] 创建接口...")
            self.interface = LibSignalInterface(
                sim=self.simulation, 
                sys=self.solver,
                junction_manager=self.junction_manager,
                step_delay=self.step_delay
            )
            self.simulation.set_interface(self.interface)
            self.solver.set_interface(self.interface)
            
            # 5. 更新网络数据
            self.simulation.update_netdata()
            
            # 6. 从网络数据初始化JunctionAgent
            print("[DashboardController] 初始化JunctionAgent...")
            network_data = self.interface.get_netdata()
            self.junction_manager.initialize_from_network_data(network_data)
            
            self.is_initialized = True
            print(f"[DashboardController] 系统初始化完成 (共 {len(self.junction_manager.junctions)} 个路口)")
            
        except Exception as e:
            print(f"[DashboardController] 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def start(self):
        """启动仿真"""
        if not self.is_initialized:
            self.initialize()
        
        if self.is_running:
            return
        
        self.simulation.start()
        self.is_running = True
    
    def step(self):
        """
        执行一个仿真步骤
        
        流程：
        1. SUMO生成车辆
        2. 更新订阅数据缓存
        3. 获取当前状态
        4. 智能体决策
        5. 应用决策
        6. 更新JunctionAgent
        7. SUMO执行一步
        8. 返回更新后的数据
        """
        if not self.is_running:
            raise RuntimeError("仿真未启动，请先调用start()")
        
        # 1. SUMO执行一步（先推进仿真，更新观察数据）
        self.simulation.sim_step()
        
        # 2. 生成车辆
        if self.simulation.vehiclegen:
            self.simulation.vehiclegen.run()
        
        # 3. 更新通行时间
        self.simulation.update_travel_times()
        
        # 4. 信号更新（智能体决策）- 此时 full_observation 已是最新
        self.simulation.signal_complete = False
        self.interface.signal_update()
        while self.simulation.signal_complete != True:
            continue
        
        # 5. 更新JunctionAgent数据
        if self.current_step == 0:  # 第一步
            print(f"[DashboardController.step] 准备更新JunctionAgent数据...")
        self._update_junction_agents()
        
        if self.current_step == 0:  # 第一步
            print(f"[DashboardController.step] JunctionAgent数据更新完成")
        
        # 6. 如果设置了延迟（无GUI模式），等待指定时间
        # 注意：延迟在 current_step 增加之前执行，使用当前值判断
        if self.current_step == 0:
            # 第一步输出延迟配置
            print(f"\n[DashboardController] ========== 延迟配置 ==========")
            print(f"step_delay = {self.step_delay} (类型: {type(self.step_delay)})")
            print(f"args.step_delay = {getattr(self.args, 'step_delay', 'NOT_SET')}")
            print(f"args.nogui = {getattr(self.args, 'nogui', 'NOT_SET')}")
            print(f"判断 step_delay > 0: {self.step_delay > 0}")
            print(f"==========================================\n")
        
        # 延迟控制
        if self.step_delay > 0:
            time.sleep(self.step_delay)
            # 每20步输出一次确认
            if self.current_step % 20 == 0:
                print(f"[DELAY] Step {self.current_step + 1}: 延迟 {self.step_delay}s")
        elif self.current_step == 0:
            print(f"[DashboardController] 警告: step_delay={self.step_delay}，未启用延迟")
        
        self.current_step += 1
        
        # 7. 返回当前状态
        return self.get_current_state()
    
    def _update_junction_agents(self):
        """从订阅缓存更新JunctionAgent数据"""
        subscription_cache = self.interface.subscription_cache
        
        # 调试：检查订阅缓存
        lane_data = subscription_cache.get('lane_data', {})
        tl_data = subscription_cache.get('traffic_light_data', {})
        
        if self.current_step == 1:
            print(f"[_update_junction_agents] 订阅缓存: {len(lane_data)} 条车道数据, {len(tl_data)} 条信号灯数据")
            if lane_data:
                # 找一条有车的车道
                sample_lane = None
                for lane_id, data in lane_data.items():
                    if data.get('vehicle_number', 0) > 0:
                        sample_lane = lane_id
                        break
                if sample_lane:
                    print(f"[_update_junction_agents] 有车车道示例 {sample_lane}: {lane_data[sample_lane]}")
                else:
                    sample_lane = list(lane_data.keys())[0]
                    print(f"[_update_junction_agents] 无车车道示例 {sample_lane}: {lane_data[sample_lane]}")
        
        # 更新车道数据
        updated_junctions = set()
        for lane_id, data in lane_data.items():
            # 查找该车道属于哪个路口
            junction_id = self._find_junction_for_lane(lane_id)
            if junction_id:
                junction = self.junction_manager.get_junction(junction_id)
                if junction:
                    junction.update_lane_data(
                        lane_id=lane_id,
                        vehicle_count=data.get('vehicle_number', 0),
                        mean_speed=data.get('mean_speed', 0.0),
                        occupancy=data.get('occupancy', 0.0),
                        halting_count=data.get('halting_number', 0)
                    )
                    updated_junctions.add(junction_id)
        
        if self.current_step == 1:
            print(f"[_update_junction_agents] 更新了 {len(updated_junctions)} 个路口的车道数据")
        
        # 更新交通信号灯数据
        for tl_id, data in tl_data.items():
            junction = self.junction_manager.get_junction(tl_id)
            if junction and junction.traffic_light_state:
                junction.update_traffic_light(
                    phase_state=data.get('phase_state', ''),
                    phase_duration=data.get('phase_duration', 0.0),
                    next_switch_time=data.get('next_switch', 0.0)
                )
        
        # 计算所有路口的指标
        if self.current_step == 1:
            print(f"[_update_junction_agents] 开始计算 {len(self.junction_manager.junctions)} 个路口的指标")
        self.junction_manager.update_all_metrics()
    
    def _find_junction_for_lane(self, lane_id):
        """根据车道ID查找所属路口"""
        # 优化：使用缓存的映射关系
        if not hasattr(self, '_lane_to_junction_cache'):
            self._lane_to_junction_cache = {}
        
        # 如果缓存为空，建立映射
        if not self._lane_to_junction_cache:
            netdata = self.interface.get_netdata()
            
            print(f"[_find_junction_for_lane] netdata keys: {netdata.keys()}")
            
            if 'inter' in netdata:
                print(f"[_find_junction_for_lane] inter中有 {len(netdata['inter'])} 个路口")
                # 输出一个路口示例
                if netdata['inter']:
                    sample_junc_id = list(netdata['inter'].keys())[0]
                    sample_junc = netdata['inter'][sample_junc_id]
                    print(f"[_find_junction_for_lane] 示例路口 {sample_junc_id}:")
                    print(f"  - incoming_lanes: {sample_junc.get('incoming_lanes', [])[: 3]}...")
                    print(f"  - outgoing_lanes: {sample_junc.get('outgoing_lanes', [])[: 3]}...")
                
                for junction_id, junction_info in netdata['inter'].items():
                    for lane in junction_info.get('incoming_lanes', []):
                        self._lane_to_junction_cache[lane] = junction_id
                    for lane in junction_info.get('outgoing_lanes', []):
                        self._lane_to_junction_cache[lane] = junction_id
                
                print(f"[_find_junction_for_lane] 建立车道映射缓存: {len(self._lane_to_junction_cache)} 条映射")
                # 输出几个示例
                sample_lanes = list(self._lane_to_junction_cache.items())[:5]
                for lane, junction in sample_lanes:
                    print(f"  - {lane} -> {junction}")
        
        result = self._lane_to_junction_cache.get(lane_id)
        if result is None and self.current_step == 1:
            # 在第1步输出未找到的车道示例
            if not hasattr(self, '_unmapped_lanes_shown'):
                self._unmapped_lanes_shown = set()
            if lane_id not in self._unmapped_lanes_shown and len(self._unmapped_lanes_shown) < 5:
                print(f"[_find_junction_for_lane] 警告: 找不到车道 {lane_id} 对应的路口")
                self._unmapped_lanes_shown.add(lane_id)
        return result
    
    def get_current_state(self):
        """获取当前仿真状态"""
        # 安全获取仿真时间
        sim_time = self.simulation.current_time if self.simulation else 0.0
        
        return {
            'current_step': self.current_step,
            'total_steps': self.total_steps,
            'simulation_time': sim_time,
            'junctions': self.junction_manager.get_all_summaries()
        }
    
    def get_junction_detail(self, junction_id):
        """获取指定路口的详细信息"""
        junction = self.junction_manager.get_junction(junction_id)
        if junction:
            return junction.get_state_dict()
        return None
    
    def run_full_simulation(self):
        """运行完整的仿真（执行指定步数的仿真循环，支持前端实时查询）"""
        if not self.is_initialized:
            self.initialize()
        
        if not self.is_running:
            self.start()
        
        # 执行仿真循环
        print(f"[DashboardController] 开始运行仿真，总步数: {self.total_steps}，延迟: {self.step_delay}s")
        
        for step in range(self.total_steps):
            try:
                self.step()
                
                # 每一步都输出进度（调试用）
                if True:  # 可以改成 (step + 1) % 100 == 0 来减少输出
                    state = self.get_current_state()
                    if state['junctions']:
                        # 使用 total_halting 作为队列长度的近似
                        avg_halting = sum(j.get('total_halting', 0) for j in state['junctions']) / len(state['junctions'])
                        avg_vehicles = sum(j.get('total_vehicles', 0) for j in state['junctions']) / len(state['junctions'])
                        total_vehicles = sum(j.get('total_vehicles', 0) for j in state['junctions'])
                        print(f"[Dashboard] Step {step + 1}/{self.total_steps}: "
                              f"总车辆={total_vehicles}, 平均停车数={avg_halting:.2f}, 平均车辆数={avg_vehicles:.2f}")
                
                # 短暂让出CPU，允许其他线程（如前端API）查询状态
                if self.step_delay == 0:
                    time.sleep(0.001)  # 即使无延迟，也让出1ms给前端查询
                
            except Exception as e:
                print(f"[DashboardController] 步进失败 (步数 {step}): {e}")
                import traceback
                traceback.print_exc()
                break
        
        self.is_running = False
        print(f"[DashboardController] 仿真完成，总共执行了 {self.current_step} 步")
    
    def stop(self):
        """停止仿真"""
        if self.is_running:
            if self.simulation:
                self.simulation.close()
            self.is_running = False
            print("[DashboardController] 仿真已停止")
    
    def reset(self):
        """重置仿真状态"""
        self.stop()
        self.is_initialized = False
        self.is_running = False
        self.current_step = 0
        self.junction_manager.reset_all()
        print("[DashboardController] 系统已重置")


def main():
    """测试函数"""
    import sys
    
    # 测试参数
    test_args = [
        '-sim', '81',
        '-tsc', 'maxpressure',
        '-demand', 'fixed',
        '-nogui',
        '-simlen', '100',  # 测试时只运行100步
        '-mode', 'test'
    ]
    
    print("=" * 60)
    print("测试 DashboardController")
    print("=" * 60)
    
    try:
        # 创建控制器
        controller = DashboardController(test_args)
        
        # 运行仿真
        controller.run_full_simulation()
        
        # 显示最终状态
        print("\n" + "=" * 60)
        print("最终状态")
        print("=" * 60)
        state = controller.get_current_state()
        print(f"完成步数: {state['current_step']}/{state['total_steps']}")
        print(f"路口数量: {len(state['junctions'])}")
        
        # 显示前3个路口的详细信息
        print("\n前3个路口详情:")
        for i, junction_summary in enumerate(state['junctions'][:3]):
            junction_id = junction_summary['junction_id']
            detail = controller.get_junction_detail(junction_id)
            if detail:
                print(f"\n路口 {junction_id}:")
                print(f"  拥堵级别: {detail['metrics']['congestion_level']:.2f}")
                print(f"  车辆数: {detail['metrics']['total_vehicles']}")
                print(f"  平均速度: {detail['metrics']['average_speed']:.2f}")
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
