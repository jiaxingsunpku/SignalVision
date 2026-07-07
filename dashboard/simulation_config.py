"""
SUMO仿真配置生成器
根据当前加载的地图生成仿真启动参数
"""

from pathlib import Path
import json
import os
import sys


class SimulationConfig:
    """仿真配置类"""
    
    # 预设配置模板
    PRESETS = {
        'colight': {
            'tsc': 'colight',
            'mode': 'test',
            'nogui': True,           # Dashboard推理默认不显示GUI
            'enable_db': False,      # Dashboard推理默认不启用数据库
            'step_delay': 0.1,       # 无GUI模式下添加延迟，便于观察和控制
            'description': 'CoLight算法推理 (无GUI)'
        },
        'colight_gui': {
            'tsc': 'colight',
            'mode': 'test',
            'step_delay': 0.0,       # GUI模式下SUMO自带延迟
            'nogui': False,          # 显示SUMO GUI
            'enable_db': True,       # 启用数据库
            'description': 'CoLight算法推理 (带可视化)'
        },
        'colight_db': {
            'tsc': 'colight',
            'mode': 'test',
            'nogui': True,           # 不显示GUI
            'enable_db': True,       # 启用数据库
            'description': 'CoLight算法推理 (数据库模式)'
        },
        'maxpressure': {
            'tsc': 'maxpressure',
            'mode': 'test',
            'nogui': True,
            'enable_db': False,
            'step_delay': 0.1,
            'description': 'MaxPressure算法推理 (无GUI)'
        },
        'maxpressure_gui': {
            'tsc': 'maxpressure',
            'mode': 'test',
            'step_delay': 0.0,
            'nogui': False,
            'enable_db': True,
            'description': 'MaxPressure算法推理 (带可视化)'
        },
        'fixedtime': {
            'tsc': 'fixedtime',
            'mode': 'test',
            'nogui': True,
            'enable_db': False,
            'step_delay': 0.1,
            'description': 'FixedTime算法推理 (无GUI)'
        },
        'fixedtime_gui': {
            'tsc': 'fixedtime',
            'mode': 'test',
            'step_delay': 0.0,
            'nogui': False,
            'enable_db': True,
            'description': 'FixedTime算法推理 (带可视化)'
        },
        'ppo': {
            'tsc': 'ppo',
            'mode': 'test',
            'nogui': True,
            'enable_db': False,
            'step_delay': 0.1,
            'description': 'PPO-PFRL算法推理 (无GUI)'
        },
        'ppo_gui': {
            'tsc': 'ppo',
            'mode': 'test',
            'step_delay': 0.0,
            'nogui': False,
            'enable_db': True,
            'description': 'PPO-PFRL算法推理 (带可视化)'
        }
    }
    
    # 默认参数（LibSignal格式）
    DEFAULT_ARGS = {
        # 邻接矩阵参数
        'normalized_k': 0.5,
        
        # 仿真参数
        'sim': '81',  # LibSignal默认场景，将被动态替换
        'demand': 'onfly',  # LibSignal使用在线流量生成
        'gmin': 1,
        'r': 3,
        'y': 5,  # LibSignal黄灯时长
        'simlen': 3600,
        'scale': 2,
        'render_interval': 400,
        'offset': 0.05,
        'port': 8020,
        
        # 可视化和数据库（由预设配置决定）
        # 'nogui' 和 'enable_db' 将在预设中设置
        
        # 强化学习/训练参数
        'pi_lr': 2e-4,
        'vf_lr': 2e-4,
        'encoder_lr': 0.005,
        'clip_ratio': 0.4,
        'target_freq': 128,
        'n_iters': 30,
        'n_epochs': 100,
        'test_epoch': 1000,
        'gamma': 0.95,
        'gae_lambda': 0.9,
        'kl_coef': 0.5,
        'metrics_args': 'pressure',
        
        # 批处理和缓存参数
        'batch': 64,
        'buffer_size': 200,
        'slice_length': 150,
        'num_cpu': 1,
        
        # 模型结构参数
        'mlp_size': 128,
        'n_layers': 2,
        'gnn_size': 32,
        'hidden_act': 'relu',
        
        # 保存标志
        'save': True,
        'save_epochs': 5,
    }
    
    def __init__(self, project_root):
        """
        初始化配置生成器
        
        Args:
            project_root: 项目根目录
        """
        self.project_root = Path(project_root)
        self.dashboard_config = self._load_dashboard_config()
        self.inference_config = self._load_inference_config()
    
    def _load_dashboard_config(self):
        """加载Dashboard配置文件"""
        config_path = self.project_root / 'dashboard' / 'config.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_inference_config(self):
        """加载推理配置文件"""
        config_path = self.project_root / 'dashboard' / 'inference_config.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def get_current_map(self):
        """获取当前地图名称"""
        return os.environ.get(
            'SUMO_MAP_NAME',
            self.dashboard_config.get('map', {}).get('default_map', '81')
        )
    
    def generate_args(self, preset='maxpressure', sim_name=None, inference_mode='inference', **overrides):
        """
        生成仿真启动参数
        
        Args:
            preset: 预设配置名称 ('maxpressure' 或 'ppo')
            sim_name: 场景名称（如果不指定，使用dashboard配置中的地图）
            inference_mode: 推理模式 ('inference', 'inference_with_visualization', 'inference_quick', 'inference_full')
            **overrides: 覆盖的参数
            
        Returns:
            list: 命令行参数列表
        """
        # 如果没有指定场景名称，使用当前地图
        if sim_name is None:
            sim_name = self.get_current_map()
        
        # 合并参数：默认参数 + 推理配置 + 预设参数 + 覆盖参数
        args = self.DEFAULT_ARGS.copy()
        
        # 应用推理配置的通用参数
        if 'common' in self.inference_config:
            for key, value in self.inference_config['common'].items():
                if key not in ['description', 'comment']:
                    args[key] = value
        
        # 应用推理模式配置
        if inference_mode in self.inference_config:
            mode_config = self.inference_config[inference_mode]
            for key, value in mode_config.items():
                if key not in ['description', 'comment']:
                    args[key] = value
        
        # 应用预设
        if preset in self.PRESETS:
            preset_config = self.PRESETS[preset]
            for key, value in preset_config.items():
                if key != 'description':
                    args[key] = value
        
        # 设置场景
        args['sim'] = sim_name
        
        # 应用覆盖参数
        args.update(overrides)
        
        # 转换为命令行参数列表（按照原始脚本的顺序）
        # 参考 maxpressure_test.sh 的参数顺序
        param_order = [
            # 邻接矩阵参数
            'normalized_k',
            # 仿真参数
            'sim', 'demand', 'gmin', 'r', 'y', 'simlen', 'scale', 
            'render_interval', 'offset', 'port',
            # 可视化
            'nogui',
            # 数据库
            'enable_db',
            # Dashboard特有参数
            'step_delay',
            # 加载模型
            'resume', 'resume_path',
            # 模式和算法
            'mode', 'tsc',
            # 强化学习/训练参数
            'pi_lr', 'vf_lr', 'encoder_lr', 'clip_ratio', 'target_freq',
            'n_iters', 'n_epochs', 'test_epoch', 'gamma', 'gae_lambda', 
            'kl_coef', 'metrics_args',
            # 批处理和缓存参数
            'batch', 'buffer_size', 'slice_length', 'num_cpu',
            # 模型结构参数
            'mlp_size', 'n_layers', 'gnn_size', 'hidden_act',
            # 保存标志
            'save', 'save_epochs',
        ]
        
        cmd_args = []
        # 按顺序添加参数
        for key in param_order:
            if key in args:
                value = args[key]
                if isinstance(value, bool):
                    if value:
                        cmd_args.append(f'-{key}')
                elif value is not None:
                    cmd_args.extend([f'-{key}', str(value)])
        
        # 添加任何不在顺序列表中的参数
        for key, value in args.items():
            if key not in param_order:
                if isinstance(value, bool):
                    if value:
                        cmd_args.append(f'-{key}')
                elif value is not None:
                    cmd_args.extend([f'-{key}', str(value)])
        
        return cmd_args
    
    def generate_command(self, preset='maxpressure', sim_name=None, inference_mode='inference', **overrides):
        """
        生成完整的运行命令
        
        Args:
            preset: 预设配置名称
            sim_name: 场景名称
            inference_mode: 推理模式
            **overrides: 覆盖的参数
            
        Returns:
            list: 完整的命令列表 ['python', 'run.py', '-arg1', 'val1', ...]
        """
        args = self.generate_args(preset, sim_name, inference_mode, **overrides)
        return [sys.executable, 'run.py'] + args
    
    def get_preset_description(self, preset):
        """获取预设描述"""
        return self.PRESETS.get(preset, {}).get('description', '未知配置')
    
    def list_presets(self):
        """列出所有可用的预设"""
        return [
            {
                'name': name,
                'description': config.get('description', ''),
                'tsc': config.get('tsc', ''),
                'mode': config.get('mode', '')
            }
            for name, config in self.PRESETS.items()
        ]


def generate_simulation_command(project_root, preset='maxpressure', sim_name=None, **kwargs):
    """
    便捷函数：生成仿真命令
    
    Args:
        project_root: 项目根目录
        preset: 预设配置
        sim_name: 场景名称
        **kwargs: 其他参数覆盖
        
    Returns:
        list: 命令列表
    """
    config = SimulationConfig(project_root)
    return config.generate_command(preset, sim_name, **kwargs)


# 测试代码
if __name__ == '__main__':
    import sys
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    
    # 创建配置生成器
    config = SimulationConfig(project_root)
    
    print("=" * 60)
    print("仿真配置生成器")
    print("=" * 60)
    
    # 显示当前地图
    current_map = config.get_current_map()
    print(f"\n当前地图: {current_map}")
    
    # 列出所有预设
    print("\n可用预设:")
    for preset in config.list_presets():
        print(f"  - {preset['name']}: {preset['description']}")
        print(f"    算法: {preset['tsc']}, 模式: {preset['mode']}")
    
    # 生成MaxPressure命令
    print("\n" + "=" * 60)
    print("MaxPressure命令 (使用当前地图)")
    print("=" * 60)
    cmd = config.generate_command('maxpressure')
    print(' '.join(cmd))
    
    # 生成PPO命令
    print("\n" + "=" * 60)
    print("PPO命令 (使用当前地图)")
    print("=" * 60)
    cmd = config.generate_command('ppo')
    print(' '.join(cmd))
    
    # 生成自定义命令
    print("\n" + "=" * 60)
    print("自定义命令 (指定地图和参数)")
    print("=" * 60)
    cmd = config.generate_command('maxpressure', sim_name='hangzhou', simlen=7200, nogui=True)
    print(' '.join(cmd))
