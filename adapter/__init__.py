"""
Dashboard 适配层

这个模块提供标准化接口，让 Dashboard 前端能够与不同的运行时系统对接。
当前实现：LibSignal 运行时适配器

设计理念：
- Dashboard 只依赖标准接口（抽象基类）
- 具体运行时系统通过适配器实现标准接口
- 配置转换在适配器内部完成
"""

from .standard_interface import (
    StandardSimulation,
    StandardSolver,
    StandardInterface,
    StandardArgs
)

from .libsignal_adapter import (
    LibSignalSimulation,
    LibSignalSolver,
    LibSignalInterface,
    create_libsignal_args
)

from .config_converter import ConfigConverter
from .network_data_loader import (
    NetworkDataLoader,
    SumoNetworkDataLoader,
    CityFlowNetworkDataLoader,
    load_network_from_runtime,
    load_network_from_trainer,
    save_network_data_cache,
    load_network_data_cache
)

__all__ = [
    # 标准接口
    'StandardSimulation',
    'StandardSolver',
    'StandardInterface',
    'StandardArgs',
    
    # LibSignal适配器
    'LibSignalSimulation',
    'LibSignalSolver',
    'LibSignalInterface',
    'create_libsignal_args',
    
    # 工具
    'ConfigConverter',
    
    # 网络数据加载
    'NetworkDataLoader',
    'SumoNetworkDataLoader',
    'CityFlowNetworkDataLoader',
    'load_network_from_runtime',
    'load_network_from_trainer',
    'save_network_data_cache',
    'load_network_data_cache',
]

__version__ = '1.0.0'
