"""
配置转换工具

将 Dashboard 的参数格式转换为 LibSignal 原始 run.py 期望的参数格式。
"""

from typing import Any, Dict, List, Optional

try:
    from .standard_interface import StandardArgs
except ImportError:
    from standard_interface import StandardArgs


class ConfigConverter:
    """
    配置转换器

    职责：
    1. 将 StandardArgs 转换为 LibSignal 原始 CLI 参数对象
    2. 处理 Dashboard 算法别名和 LibSignal agent 名称映射
    3. 处理 Dashboard 场景别名和 LibSignal network/cfg 名称映射
    """

    AGENT_ALIASES = {
        'colight': 'colight_pytorch_agent',
        'colight_pytorch': 'colight_pytorch_agent',
        'colight_pytorch_agent': 'colight_pytorch_agent',
        'colight_legacy': 'colight',
        'ppo': 'ppo_pfrl',
        'ppo_pfrl': 'ppo_pfrl',
        'ppo_libsignal': 'ppo',
        'maxpressure': 'maxpressure',
        'fixedtime': 'fixedtime',
        'dqn': 'dqn',
        'sotl': 'sotl',
        'frap': 'frap',
        'mplight': 'mplight',
        'presslight': 'presslight',
        'maddpg_v2': 'maddpg_v2',
        'magd': 'magd',
    }

    SUMO_SCENARIO_MAPPING = {
        '81': '81',
        'sumo81': 'sumo81',
        'ezhou': 'ezhou',
        'guanggu': 'guanggu',
        'output': 'output',
        'hangzhou': 'hangzhou',
        'sumohz4x4': 'sumohz4x4',
        'manhattan': 'manhattan',
        'sumo7x28': 'sumo7x28',
    }

    CITYFLOW_SCENARIO_MAPPING = {
        'cityflow1x1': 'cityflow1x1',
        'cityflow1x1_config2': 'cityflow1x1_config2',
        'cityflow1x1_config3': 'cityflow1x1_config3',
        'cityflow1x1_config4': 'cityflow1x1_config4',
        'cityflow1x3': 'cityflow1x3',
        'cityflow4x4': 'cityflow4x4',
        'cityflow4x4_hetero': 'cityflow4x4_hetero',
        'cityflow7x28': 'cityflow7x28',
        'cityflow_cologne1': 'cityflow_cologne1',
        'cityflow_cologne3': 'cityflow_cologne3',
        'cityflow_compare': 'cityflow_compare',
        'cityflow_grid4x4': 'cityflow_grid4x4',
    }

    DEFAULT_PREFIX = {
        ('colight_pytorch_agent', '81'): 'test',
        ('colight_pytorch_agent', 'sumo81'): 'test',
        ('colight_pytorch_agent', 'manhattan'): 'test',
        ('colight_pytorch_agent', 'sumo7x28'): 'test',
        ('ppo_pfrl', 'ezhou'): 'ppo_pfrl_ezhou',
    }

    DEFAULT_LOAD_EPISODE = {
        ('colight_pytorch_agent', '81'): 40,
        ('colight_pytorch_agent', 'sumo81'): 40,
        ('colight_pytorch_agent', 'manhattan'): 160,
        ('colight_pytorch_agent', 'sumo7x28'): 160,
        ('ppo_pfrl', 'ezhou'): 100,
    }

    # 向后兼容旧代码中的常量名称。
    ALGORITHM_MAPPING = AGENT_ALIASES
    SCENARIO_MAPPING = SUMO_SCENARIO_MAPPING

    @classmethod
    def resolve_world(cls, world: Optional[str]) -> str:
        normalized = (world or 'sumo').lower().strip()
        return 'cityflow' if normalized == 'cityflow' else 'sumo'

    @classmethod
    def _normalize_algorithm(cls, algorithm: str) -> str:
        return (algorithm or 'colight').replace('_gui', '').replace('_db', '').strip()

    @classmethod
    def resolve_agent(cls, algorithm: str) -> str:
        normalized = cls._normalize_algorithm(algorithm)
        return cls.AGENT_ALIASES.get(normalized, normalized)

    @classmethod
    def resolve_network(cls, scenario: str, world: str) -> str:
        world = cls.resolve_world(world)
        normalized = (scenario or '').strip()
        if world == 'cityflow':
            return cls.CITYFLOW_SCENARIO_MAPPING.get(normalized, normalized or 'cityflow1x1')
        return cls.SUMO_SCENARIO_MAPPING.get(normalized, normalized or 'sumo81')

    @classmethod
    def _get_default_prefix(cls, agent_name: str, network_name: str) -> str:
        return cls.DEFAULT_PREFIX.get((agent_name, network_name), 'test')

    @classmethod
    def _get_default_load_episode(cls, agent_name: str, network_name: str) -> Optional[int]:
        return cls.DEFAULT_LOAD_EPISODE.get((agent_name, network_name))

    @classmethod
    def standard_to_libsignal(cls, std_args: StandardArgs) -> Any:
        """
        将 StandardArgs 转换为 LibSignal 参数对象。
        """
        class LibSignalArgs:
            pass

        args = LibSignalArgs()

        args.task = 'tsc'
        args.world = cls.resolve_world(std_args.world)
        args.agent = cls.resolve_agent(std_args.tsc)
        args.network = cls.resolve_network(std_args.sim, args.world)
        args.dataset = std_args.dataset or 'onfly'
        args.flow_file = std_args.flow_file
        args.combined_file = std_args.combined_file

        args.interface = std_args.interface
        args.gui = not std_args.nogui
        args.delay_type = std_args.delay_type

        args.thread_num = std_args.thread_num
        args.ngpu = std_args.ngpu
        args.seed = std_args.seed
        args.debug = std_args.debug

        args.prefix = std_args.prefix or cls._get_default_prefix(args.agent, args.network)
        args.load_model = std_args.load_model
        args.test_model = std_args.test_model
        args.train_model = std_args.train_model

        load_episode = std_args.load_episode
        if load_episode is None:
            load_episode = cls._get_default_load_episode(args.agent, args.network)
        if load_episode is not None:
            args.load_episode = load_episode

        return args

    @classmethod
    def dashboard_config_to_standard(cls, config: Dict[str, Any]) -> StandardArgs:
        """
        将 Dashboard 配置字典转换为 StandardArgs。
        """
        std_args = StandardArgs()

        std_args.tsc = cls._normalize_algorithm(config.get('config', config.get('tsc', 'colight')))
        std_args.sim = config.get('sim_name', config.get('sim', '81'))
        std_args.world = cls.resolve_world(config.get('world', config.get('simulator', 'sumo')))
        std_args.mode = config.get('mode', 'test')

        std_args.nogui = config.get('nogui', True)
        std_args.enable_db = config.get('enable_db', False)

        std_args.simlen = config.get('simlen', 3600)
        std_args.gmin = config.get('gmin', 1)
        std_args.r = config.get('r', 3)
        std_args.y = config.get('y', 2)

        std_args.demand = config.get('demand', 'fixed')
        std_args.scale = config.get('scale', 2.0)
        std_args.flow_file = config.get('flow_file', '')
        std_args.combined_file = config.get('combined_file')

        std_args.render_interval = config.get('render_interval', 400)
        std_args.step_delay = config.get('step_delay', 0.0)

        std_args.port = config.get('port', 8020)
        std_args.normalized_k = config.get('normalized_k', 0.5)
        std_args.offset = config.get('offset', 0.05)

        std_args.interface = config.get(
            'interface',
            'traci' if (std_args.world == 'sumo' and not std_args.nogui) else 'libsumo'
        )

        std_args.dataset = config.get('dataset', 'onfly')
        std_args.prefix = config.get('prefix', config.get('model_name', ''))
        std_args.load_model = config.get('load_model', True)
        std_args.test_model = config.get('test_model', True)
        std_args.train_model = config.get('train_model', False)
        std_args.thread_num = config.get('thread_num', 4)
        std_args.ngpu = str(config.get('gpu', config.get('ngpu', '0')))
        std_args.seed = config.get('seed')
        std_args.debug = config.get('debug', False)
        std_args.delay_type = config.get('delay_type', 'apx')

        load_episode = config.get('load_episode', config.get('epoch'))
        if load_episode not in (None, '', 'N/A', 'latest'):
            try:
                std_args.load_episode = int(load_episode)
            except (TypeError, ValueError):
                std_args.load_episode = None

        return std_args

    @classmethod
    def get_algorithm_display_name(cls, libsignal_agent: str) -> str:
        reverse_mapping = {v: k for k, v in cls.AGENT_ALIASES.items()}
        return reverse_mapping.get(libsignal_agent, libsignal_agent)

    @classmethod
    def validate_scenario(cls, scenario: str, world: str = 'sumo') -> bool:
        scenario = (scenario or '').strip()
        if not scenario:
            return False
        return bool(cls.resolve_network(scenario, world))

    @classmethod
    def validate_algorithm(cls, algorithm: str) -> bool:
        return bool(cls.resolve_agent(algorithm))

    @classmethod
    def get_supported_scenarios(cls) -> List[str]:
        return sorted(
            set(cls.SUMO_SCENARIO_MAPPING.keys()) |
            set(cls.SUMO_SCENARIO_MAPPING.values()) |
            set(cls.CITYFLOW_SCENARIO_MAPPING.keys()) |
            set(cls.CITYFLOW_SCENARIO_MAPPING.values())
        )

    @classmethod
    def get_supported_algorithms(cls) -> List[str]:
        return sorted(set(cls.AGENT_ALIASES.keys()) | set(cls.AGENT_ALIASES.values()))
