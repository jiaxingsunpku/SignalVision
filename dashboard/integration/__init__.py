"""
Dashboard Integration Package

集成SUMO仿真、智能体系统和JunctionAgent的中间层
"""

from .junction_agent import JunctionAgent, JunctionManager

# DashboardController 延迟导入，避免在不需要时加载整个SUMO系统
def get_dashboard_controller():
    """延迟导入DashboardController"""
    from .dashboard_controller import DashboardController
    return DashboardController

__all__ = ['JunctionAgent', 'JunctionManager', 'get_dashboard_controller']

