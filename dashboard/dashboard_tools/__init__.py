"""
Dashboard 工具模块。

当前只保留与推理平台配套的辅助工具。
"""

# 工具模块延迟导入，避免循环依赖
__all__ = [
    'DataController',
    'ModelsController',
    'ComparisonController'
]

def get_data_controller():
    """获取数据控制器"""
    from .realtime_traffic_data_controller import DataController
    return DataController

def get_models_controller():
    """获取模型管理控制器"""
    from .models_controller import ModelsController
    return ModelsController

def get_comparison_controller():
    """获取持续学习控制器"""
    from .continual_learning_controller import ComparisonController
    return ComparisonController
