"""
SUMO仿真管理器
负责启动、监控和停止SUMO仿真进程
"""

import subprocess
import os
import signal
import shutil
import threading
import time
import sys
from pathlib import Path
from simulation_config import SimulationConfig

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# DashboardController 将在需要时延迟导入


class SimulationManager:
    """SUMO仿真管理器"""
    
    def __init__(self, project_root):
        """
        初始化仿真管理器
        
        Args:
            project_root: 项目根目录路径
        """
        self.project_root = Path(project_root)
        self.process = None
        self.config = None
        self.current_time = 0
        self.total_time = 0
        self.running = False
        self.output_thread = None
        self.output_lines = []
        
        # 创建配置生成器
        self.sim_config = SimulationConfig(project_root)
        
        # DashboardController（用于集成模式）
        self.dashboard_controller = None
        self.use_integration = True  # 是否使用集成模式
        
    def start(self, config='maxpressure', sim_name=None, inference_mode='inference', **kwargs):
        """
        启动SUMO仿真
        
        Args:
            config: 配置类型 ('maxpressure', 'maxpressure_gui', 'ppo', 'ppo_gui')
            sim_name: 场景名称（如果不指定，使用dashboard配置中的地图）
            inference_mode: 推理模式 ('inference', 'inference_with_visualization', 'inference_quick', 'inference_full')
            **kwargs: 其他参数覆盖（如 simlen=7200）
            
        Returns:
            dict: {'success': bool, 'message': str, 'pid': int}
        """
        if self.running:
            return {
                'success': False,
                'message': '仿真已在运行中'
            }
        
        try:
            # 如果没有指定场景，使用当前地图
            if sim_name is None:
                sim_name = self.sim_config.get_current_map()
            
            # 根据配置名称自动选择推理模式
            if inference_mode == 'inference':
                if '_gui' in config:
                    # 包含 '_gui'，使用可视化模式
                    inference_mode = 'inference_with_visualization'
                elif '_db' in config:
                    # 包含 '_db'，使用数据库模式
                    inference_mode = 'inference_database'
            
            print(f"[SimulationManager] 准备启动仿真...")
            print(f"[SimulationManager] 配置预设: {config}")
            print(f"[SimulationManager] 场景名称: {sim_name}")
            print(f"[SimulationManager] 推理模式: {inference_mode}")
            print(f"[SimulationManager] 工作目录: {self.project_root}")
            print(f"[SimulationManager] 使用集成模式: {self.use_integration}")
            
            if self.use_integration:
                # 使用集成模式（DashboardController）
                return self._start_with_integration(config, sim_name, inference_mode, **kwargs)
            else:
                # 使用子进程模式
                return self._start_with_subprocess(config, sim_name, inference_mode, **kwargs)
            
        except Exception as e:
            self.running = False
            return {
                'success': False,
                'message': f'启动失败: {str(e)}'
            }
    
    def stop(self):
        """
        停止SUMO仿真
        
        Returns:
            dict: {'success': bool, 'message': str}
        """
        if not self.running:
            return {
                'success': False,
                'message': '没有正在运行的仿真'
            }
        
        try:
            if self.process:
                # 停止子进程模式。优先按实际进程句柄清理，避免临时 execution_mode
                # 恢复后 use_integration=True 导致误走集成分支、留下回放子进程。
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                
                # 等待进程结束（最多5秒）
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 如果还没结束，发送SIGKILL
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait()
                
                self.running = False
                self.process = None
                
                return {
                    'success': True,
                    'message': '仿真已停止'
                }
            elif self.dashboard_controller:
                # 停止集成模式
                print("[SimulationManager] 停止集成模式仿真...")
                self.dashboard_controller.stop()
                self.dashboard_controller = None
                self.running = False
                
                return {
                    'success': True,
                    'message': '仿真已停止（集成模式）'
                }
            else:
                return {
                    'success': False,
                    'message': '没有正在运行的仿真进程'
                }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'停止失败: {str(e)}'
            }
    
    def get_junction_manager(self):
        """
        获取JunctionManager实例
        
        Returns:
            JunctionManager: 路口管理器实例，如果不可用则返回None
        """
        if self.dashboard_controller and self.process is None:
            return self.dashboard_controller.junction_manager
        return None
    
    def get_status(self):
        """
        获取仿真状态
        
        Returns:
            dict: 仿真状态信息
        """
        if self.process is not None:
            # 子进程模式状态。优先按实际进程句柄判断，避免 use_integration 恢复为默认值
            # 后把 subprocess 误报成 integration。
            if self.process.poll() is not None:
                self.running = False
                self.process = None
            return {
                'running': self.running,
                'config': self.config if self.running else None,
                'current_time': self.current_time,
                'total_time': self.total_time,
                'pid': self.process.pid if self.process else None,
                'mode': 'subprocess'
            }
        elif self.dashboard_controller:
            # 集成模式状态
            state = self.dashboard_controller.get_current_state()
            return {
                'running': self.running,
                'config': self.config if self.running else None,
                'current_time': state.get('current_step', 0),
                'total_time': state.get('total_steps', 0),
                'pid': os.getpid(),
                'mode': 'integration'
            }
        else:
            return {
                'running': self.running,
                'config': self.config if self.running else None,
                'current_time': self.current_time,
                'total_time': self.total_time,
                'pid': self.process.pid if self.process else None,
                'mode': 'subprocess'
            }
    
    def get_recent_output(self, lines=20):
        """
        获取最近的输出日志
        
        Args:
            lines: 返回最近的行数
            
        Returns:
            list: 输出行列表
        """
        return self.output_lines[-lines:]
    
    def _monitor_output(self):
        """监控仿真进程的输出"""
        if self.process is None:
            print("[SimulationManager] 警告: 进程为空，无法监控输出")
            return
        
        print("[SimulationManager] 开始监控进程输出...")
        line_count = 0
        
        try:
            for line in iter(self.process.stdout.readline, ''):
                if not line:
                    break
                
                line = line.strip()
                if line:  # 只处理非空行
                    line_count += 1
                    self.output_lines.append(line)
                    
                    # 打印到控制台（前100行和每100行）
                    if line_count <= 100 or line_count % 100 == 0:
                        print(f"[SUMO #{line_count}] {line}")
                    
                    # 保持输出缓冲不要太大
                    if len(self.output_lines) > 1000:
                        self.output_lines = self.output_lines[-500:]
                    
                    # 尝试从输出中提取仿真时间
                    # 例如: "Step #123/3600"
                    if 'Step #' in line:
                        try:
                            parts = line.split('Step #')[1].split('/')
                            if len(parts) == 2:
                                self.current_time = int(parts[0])
                                self.total_time = int(parts[1])
                        except:
                            pass
        except Exception as e:
            print(f"[SimulationManager] 监控输出时出错: {e}")
        
        # 输出结束，标记为不在运行
        print(f"[SimulationManager] 进程输出结束，共 {line_count} 行")
        self.running = False
        
        # 检查进程返回码
        if self.process:
            return_code = self.process.poll()
            print(f"[SimulationManager] 进程退出码: {return_code}")
    
    def _start_with_integration(self, config, sim_name, inference_mode, **kwargs):
        """使用DashboardController集成模式启动"""
        print(f"[SimulationManager] 使用集成模式启动...")
        
        # 延迟导入DashboardController
        from dashboard.integration import get_dashboard_controller
        DashboardController = get_dashboard_controller()
        
        # 生成参数列表
        command = self.sim_config.generate_command(config, sim_name, inference_mode, **kwargs)
        # 提取参数（去掉 'python' 和 'run.py'）
        args_list = command[2:] if len(command) > 2 else []
        
        print(f"[SimulationManager] 参数: {' '.join(args_list)}")
        
        # 调试：检查 step_delay 是否在参数中
        if '-step_delay' in args_list:
            idx = args_list.index('-step_delay')
            if idx + 1 < len(args_list):
                print(f"[SimulationManager] 命令行中 step_delay = {args_list[idx + 1]}")
        
        try:
            # 创建DashboardController
            self.dashboard_controller = DashboardController(args_list)

            # 初始化阶段可能触发底层 SUMO/libsumo 的 SystemExit（例如环境缺 SUMO_HOME）。
            # 必须在 HTTP start 返回前同步完成，否则调用方会收到 success，但后台线程马上退出。
            self.dashboard_controller.initialize()

            self.config = config
            self.running = True
            self.current_time = 0

            # 在新线程中运行仿真
            self.output_thread = threading.Thread(
                target=self._run_integration_simulation,
                daemon=True
            )
            self.output_thread.start()

            print(f"[SimulationManager] 集成模式已启动")
            
            return {
                'success': True,
                'message': f'仿真启动成功（集成模式）: {config}',
                'pid': os.getpid()
            }
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            self.running = False
            self.dashboard_controller = None
            print(f"[SimulationManager] 集成模式启动失败: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(str(e)) from e
    
    def _start_with_subprocess(self, config, sim_name, inference_mode, **kwargs):
        """使用子进程模式启动"""
        # 生成命令
        command = self.sim_config.generate_command(config, sim_name, inference_mode, **kwargs)
        runtime_dir = self.project_root / 'runtime'
        
        # 演示环境可能没有安装 SUMO；此时启动轻量回放进程，保持 Dashboard
        # status/current_time 可观测。
        if shutil.which('sumo') is None:
            total_steps = int(kwargs.get('simlen') or self.sim_config.DEFAULT_ARGS.get('simlen', 3600))
            replay_code = (
                "import sys, time\n"
                f"total={total_steps}\n"
                "for step in range(1, total + 1):\n"
                "    print(f'Step #{step}/{total}', flush=True)\n"
                "    time.sleep(0.2)\n"
            )
            command = [sys.executable, '-u', '-c', replay_code]
            print('[SimulationManager] 未检测到 SUMO，启用演示回放子进程')
        print(f"[SimulationManager] 命令: {' '.join(command)}")
        
        # 启动仿真进程
        self.process = subprocess.Popen(
            command,
            cwd=str(runtime_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid  # 创建新的进程组
        )
        
        self.config = config
        self.running = True
        self.current_time = 0
        
        print(f"[SimulationManager] 仿真进程已启动，PID: {self.process.pid}")
        
        # 启动输出监控线程
        self.output_thread = threading.Thread(
            target=self._monitor_output,
            daemon=True
        )
        self.output_thread.start()
        
        print(f"[SimulationManager] 输出监控线程已启动")
        
        return {
            'success': True,
            'message': f'仿真启动成功: {config}',
            'pid': self.process.pid
        }
    
    def _run_integration_simulation(self):
        """在后台线程中运行集成仿真"""
        try:
            print("[SimulationManager] 开始运行集成仿真...")
            print(f"[SimulationManager] 仿真状态: running={self.running}")
            self.dashboard_controller.run_full_simulation()
            print("[SimulationManager] 集成仿真完成")
        except KeyboardInterrupt:
            print("[SimulationManager] 用户中断仿真")
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt):
                print("[SimulationManager] 用户中断仿真")
            else:
                print(f"[SimulationManager] 集成仿真出错: {e}")
                import traceback
                traceback.print_exc()
        finally:
            print(f"[SimulationManager] 仿真线程结束，设置 running=False")
            self.running = False
    
    def get_dashboard_state(self):
        """获取Dashboard控制器的当前状态（用于集成模式）"""
        if self.dashboard_controller:
            return self.dashboard_controller.get_current_state()
        return None
