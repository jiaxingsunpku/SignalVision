"""
SUMO交通监控Dashboard - 后端API服务器

提供RESTful API接口供前端调用
"""

import os
import sys
import json
import pickle
import logging
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from pathlib import Path

from integration.junction_agent import JunctionManager
from simulation_manager import SimulationManager
from realtime_comparison_manager import RealtimeComparisonManager
from dashboard_tools import get_data_controller, get_models_controller, get_comparison_controller

# 导入适配器（用于加载网络数据）
sys.path.insert(0, str(Path(__file__).parent.parent))
from adapter import load_network_from_runtime, save_network_data_cache, load_network_data_cache


# 加载配置文件
def load_config():
    """加载配置文件"""
    config_path = Path(__file__).parent / "config.json"
    
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        print("[Server] 警告：config.json不存在，使用默认配置")
        return {
            "server": {"host": "0.0.0.0", "port": 8080, "debug": False},
            "map": {
                "directory": "cache",
                "default_map": "81",
                "netdata_filename": "netdata.pkl"
            },
            "dashboard": {
                "title": "交通信控系统",
                "auto_refresh": False,
                "refresh_interval": 5000
            }
        }

# 加载配置
config = load_config()


def configure_http_request_logging(debug: bool = False):
    """控制 Flask/Werkzeug 的访问日志输出。"""
    werkzeug_logger = logging.getLogger('werkzeug')
    if debug:
        werkzeug_logger.setLevel(logging.INFO)
        werkzeug_logger.disabled = False
    else:
        werkzeug_logger.setLevel(logging.ERROR)
        werkzeug_logger.disabled = False

# 创建Flask应用
app = Flask(__name__, 
            static_folder='static',
            template_folder='templates')

if config.get('api', {}).get('enable_cors', True):
    CORS(app)  # 允许跨域

# 全局路口管理器
junction_manager = JunctionManager()

# 路径配置
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_ROOT = Path(__file__).resolve().parent
MAP_DIR = DASHBOARD_ROOT / config['map']['directory']

# 全局仿真管理器
simulation_manager = SimulationManager(PROJECT_ROOT)
realtime_comparison_manager = RealtimeComparisonManager(PROJECT_ROOT)

# 全局工具控制器（延迟初始化）
data_controller = None
models_controller = None
comparison_controller = None


# ========== 静态文件路由 ==========

@app.route('/')
def index():
    """主页"""
    return send_from_directory('templates', 'index.html')


@app.route('/static/<path:path>')
def serve_static(path):
    """静态资源"""
    return send_from_directory('static', path)


# ========== API路由 ==========

@app.route('/api/config', methods=['GET'])
def get_config():
    """
    获取前端配置
    
    Returns:
        {
            "dashboard": {...},  # Dashboard配置
            "map": {...},        # 地图配置
            "success": true
        }
    """
    try:
        # 只返回前端需要的配置
        frontend_config = {
            "dashboard": config.get("dashboard", {}),
            "map": {
                "default_map": config['map'].get('default_map', '81'),
                "directory": config['map'].get('directory', 'cache')
            }
        }
        
        return jsonify({
            "config": frontend_config,
            "success": True
        })
    
    except Exception as e:
        return jsonify({
            "error": str(e),
            "success": False
        }), 500

@app.route('/api/network', methods=['GET'])
def get_network():
    """
    获取网络数据
    
    Returns:
        {
            "network_data": {...},  # 网络数据
            "junction_count": int,   # 路口数量
            "success": true
        }
    """
    try:
        if junction_manager.network_data is None:
            # 尝试加载默认地图
            print("[API] 网络数据未初始化，尝试加载默认地图...")
            default_map = load_default_network_data()
            if default_map:
                print(f"[API] 默认地图加载成功，正在初始化路口管理器...")
                junction_manager.initialize_from_network_data(default_map)
                print(f"[API] 路口管理器初始化完成，共 {len(junction_manager.junctions)} 个路口")
            else:
                print(f"[API] 错误：未找到地图文件在 {MAP_DIR}")
                return jsonify({
                    "error": f"网络数据未加载，地图目录: {MAP_DIR}",
                    "success": False
                }), 404
        
        # 转换network_data中的set为list（JSON可序列化）
        network_data_json = convert_sets_to_lists(junction_manager.network_data)
        
        return jsonify({
            "network_data": network_data_json,
            "junction_count": len(junction_manager.junctions),
            "success": True
        })
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[API] 网络数据加载失败:")
        print(error_trace)
        return jsonify({
            "error": str(e),
            "traceback": error_trace,
            "success": False
        }), 500


@app.route('/api/junctions/summary', methods=['GET'])
def get_junctions_summary():
    """
    获取所有路口的摘要信息
    
    Returns:
        {
            "summaries": [
                {
                    "junction_id": str,
                    "position": [x, y],
                    "junction_type": str,
                    "congestion_level": float,
                    ...
                },
                ...
            ],
            "count": int,
            "success": true
        }
    """
    try:
        # 仿真运行时读仿真 manager；停了（仿真 manager 残留为空）则回落全局 manager，避免路网点位消失
        manager = simulation_manager.get_junction_manager() if simulation_manager.running else None
        if manager is None:
            manager = junction_manager

        summaries = manager.get_all_summaries()
        
        return jsonify({
            "summaries": summaries,
            "count": len(summaries),
            "success": True
        })
    
    except Exception as e:
        return jsonify({
            "error": str(e),
            "success": False
        }), 500


@app.route('/api/junctions/<junction_id>', methods=['GET'])
def get_junction_detail(junction_id):
    """
    获取指定路口的详细信息
    
    Args:
        junction_id: 路口ID
    
    Returns:
        {
            "junction": {
                "junction_id": str,
                "position": [x, y],
                "incoming_lanes": {...},
                "outgoing_lanes": {...},
                "traffic_light": {...},
                "metrics": {...},
                ...
            },
            "success": true
        }
    """
    try:
        # 优先从仿真中获取JunctionManager（仿真运行时），否则使用全局的（仿真停了不读其残留空 manager）
        manager = simulation_manager.get_junction_manager() if simulation_manager.running else None
        if manager is None:
            manager = junction_manager

        if manager.network_data is None:
            return jsonify({
                "success": False,
                "message": "路口数据未加载，请先加载地图"
            }), 200
        
        agent = manager.get_junction(junction_id)
        
        if agent is None:
            return jsonify({
                "success": False,
                "message": f"路口 {junction_id} 不存在"
            }), 200
        
        # 获取状态数据
        state_dict = agent.get_state_dict()
        
        return jsonify({
            "junction": state_dict,
            "success": True
        })
    
    except Exception as e:
        print(f"[API] 获取路口详情失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"服务器错误: {str(e)}"
        }), 200


@app.route('/api/junctions/<junction_id>/update', methods=['POST'])
def update_junction_data(junction_id):
    """
    更新路口数据（供外部系统调用）
    
    POST Body:
        {
            "lane_data": {
                "lane_id": {
                    "vehicle_count": int,
                    "mean_speed": float,
                    "occupancy": float,
                    "halting_count": int
                },
                ...
            },
            "traffic_light": {
                "phase_state": str,           # 信号灯状态字符串
                "phase_duration": float,      # 当前相位已持续时间（秒）
                "next_switch_time": float     # 距离下次可能切换的时间（秒）
            }
        }
    """
    try:
        agent = junction_manager.get_junction(junction_id)
        
        if agent is None:
            return jsonify({
                "error": f"路口 {junction_id} 不存在",
                "success": False
            }), 404
        
        data = request.get_json()
        
        # 更新车道数据
        if "lane_data" in data:
            for lane_id, lane_info in data["lane_data"].items():
                agent.update_lane_data(
                    lane_id=lane_id,
                    vehicle_count=lane_info.get("vehicle_count", 0),
                    mean_speed=lane_info.get("mean_speed", 0.0),
                    occupancy=lane_info.get("occupancy", 0.0),
                    halting_count=lane_info.get("halting_count", 0)
                )
        
        # 更新信号灯状态
        if "traffic_light" in data:
            tl_data = data["traffic_light"]
            agent.update_traffic_light(
                phase_state=tl_data.get("phase_state", ""),
                phase_duration=tl_data.get("phase_duration", 0.0),
                next_switch_time=tl_data.get("next_switch_time", 0.0)
            )
        
        # 重新计算指标
        agent.calculate_metrics()
        
        return jsonify({
            "message": f"路口 {junction_id} 数据已更新",
            "success": True
        })
    
    except Exception as e:
        return jsonify({
            "error": str(e),
            "success": False
        }), 500


@app.route('/api/load-map', methods=['POST'])
def load_map():
    """
    加载地图数据
    
    POST Body:
        {
            "map_path": str  # 相对于map目录的路径
        }
    """
    try:
        data = request.get_json()
        map_path = data.get("map_path")
        
        if not map_path:
            return jsonify({
                "error": "缺少map_path参数",
                "success": False
            }), 400
        
        full_path = MAP_DIR / map_path
        
        if not full_path.exists():
            return jsonify({
                "error": f"地图文件不存在: {map_path}",
                "success": False
            }), 404
        
        # 加载网络数据
        if full_path.suffix == '.pkl':
            with open(full_path, 'rb') as f:
                network_data = pickle.load(f)
        elif full_path.suffix == '.json':
            with open(full_path, 'r', encoding='utf-8') as f:
                network_data = json.load(f)
        else:
            return jsonify({
                "error": "不支持的文件格式，仅支持.pkl和.json",
                "success": False
            }), 400
        
        # 初始化路口管理器
        junction_manager.initialize_from_network_data(network_data)
        
        return jsonify({
            "message": f"地图加载成功: {map_path}",
            "junction_count": len(junction_manager.junctions),
            "success": True
        })
    
    except Exception as e:
        return jsonify({
            "error": str(e),
            "success": False
        }), 500


@app.route('/api/maps', methods=['GET'])
def list_maps():
    """
    列出所有可用的地图
    
    Returns:
        {
            "maps": [
                {
                    "name": str,
                    "path": str,
                    "size": int
                },
                ...
            ]
        }
    """
    try:
        maps = []
        
        if MAP_DIR.exists():
            for item in MAP_DIR.iterdir():
                if item.is_dir():
                    # 查找目录中的.pkl文件
                    for pkl_file in item.glob('*.pkl'):
                        relative_path = pkl_file.relative_to(MAP_DIR)
                        maps.append({
                            "name": str(relative_path),
                            "path": str(relative_path),
                            "size": pkl_file.stat().st_size
                        })
        
        return jsonify({
            "maps": maps,
            "count": len(maps),
            "success": True
        })
    
    except Exception as e:
        return jsonify({
            "error": str(e),
            "success": False
        }), 500


# ========== 辅助函数 ==========

def convert_sets_to_lists(obj):
    """
    递归转换对象中的所有set为list，使其可JSON序列化
    """
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: convert_sets_to_lists(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets_to_lists(item) for item in obj]
    else:
        return obj


def load_default_network_data():
    """
    加载默认网络数据
    
    优先从缓存加载，如果缓存不存在，则通过适配器从 runtime 加载并缓存。
    """
    # 优先使用环境变量，其次使用配置文件
    default_map = os.environ.get('SUMO_MAP_NAME', config['map']['default_map'])
    netdata_filename = config['map']['netdata_filename']
    
    # 缓存路径
    cache_path = MAP_DIR / default_map / netdata_filename
    
    # 1. 尝试从缓存加载
    if cache_path.exists():
        try:
            print(f"[Server] 从缓存加载地图: {cache_path}")
            return load_network_data_cache(cache_path)
        except Exception as e:
            print(f"[Server] 缓存加载失败: {e}，尝试从 runtime 重新加载...")
    
    # 2. 从 runtime 通过适配器加载
    try:
        print(f"[Server] 从 runtime 加载地图: {default_map}")
        runtime_root = PROJECT_ROOT / 'runtime'
        network_data = load_network_from_runtime(default_map, runtime_root)
        
        # 保存到缓存
        save_network_data_cache(network_data, cache_path)
        print(f"[Server] 地图数据已缓存到: {cache_path}")
        
        return network_data
        
    except Exception as e:
        print(f"[Server] 从 runtime 加载失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 3. 尝试查找其他可用的缓存地图
    if MAP_DIR.exists():
        print(f"[Server] 在 {MAP_DIR} 目录查找其他缓存地图...")
        for item in MAP_DIR.iterdir():
            if item.is_dir():
                netdata_path = item / netdata_filename
                if netdata_path.exists():
                    try:
                        print(f"[Server] 找到并加载缓存地图: {netdata_path}")
                        return load_network_data_cache(netdata_path)
                    except:
                        continue
    
    print(f"[Server] 错误：无法加载地图数据")
    return None


def load_named_network_data(map_name):
    """
    按地图名称加载网络数据。

    优先从缓存读取；若缓存缺失，则回退到 runtime 配置并自动写回缓存。
    """
    netdata_filename = config['map']['netdata_filename']
    cache_path = MAP_DIR / map_name / netdata_filename

    if cache_path.exists():
        print(f"[Server] 从缓存加载指定地图: {cache_path}")
        return load_network_data_cache(cache_path)

    runtime_root = PROJECT_ROOT / 'runtime'
    print(f"[Server] 从 runtime 加载指定地图: {map_name}")
    network_data = load_network_from_runtime(map_name, runtime_root)
    save_network_data_cache(network_data, cache_path)
    print(f"[Server] 指定地图已缓存到: {cache_path}")
    return network_data


# ========== 仿真控制API ==========

@app.route('/api/simulation/start', methods=['POST'])
def start_simulation():
    """启动SUMO仿真"""
    try:
        if realtime_comparison_manager.running:
            return jsonify({
                'success': False,
                'message': '请先停止 FixedTime vs PPO 对比实验'
            }), 409
        data = request.get_json() or {}
        config_type = data.get('config', 'maxpressure')
        sim_name = data.get('sim_name')  # 可选：指定场景名称
        execution_mode = data.get('execution_mode')  # integration | subprocess，本次启动临时生效
        if execution_mode not in (None, 'integration', 'subprocess'):
            return jsonify({
                'success': False,
                'message': f"execution_mode 非法: {execution_mode!r}，允许 integration/subprocess"
            }), 400
        
        # 提取其他参数（如 simlen, nogui 等），控制字段不传入 runtime 参数。
        overrides = {k: v for k, v in data.items() if k not in ['config', 'sim_name', 'execution_mode']}
        
        print(f"[Server] 收到启动仿真请求:")
        print(f"  配置: {config_type}")
        print(f"  场景: {sim_name if sim_name else '(使用当前地图)'}")
        if execution_mode:
            print(f"  执行模式: {execution_mode}")
        if overrides:
            print(f"  参数覆盖: {overrides}")
        
        previous_use_integration = simulation_manager.use_integration
        if execution_mode:
            simulation_manager.use_integration = execution_mode == 'integration'
        try:
            result = simulation_manager.start(config_type, sim_name, **overrides)
        finally:
            simulation_manager.use_integration = previous_use_integration
        
        print(f"[Server] 仿真启动结果: {result}")
        
        return jsonify(result)
    
    except Exception as e:
        print(f"[Server] 启动仿真时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'启动失败: {str(e)}'
        }), 500


@app.route('/api/simulation/stop', methods=['POST'])
def stop_simulation():
    """停止SUMO仿真"""
    try:
        print(f"[Server] 收到停止仿真请求")
        
        result = simulation_manager.stop()
        
        print(f"[Server] 仿真停止结果: {result}")
        
        return jsonify(result)
    
    except Exception as e:
        print(f"[Server] 停止仿真时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'停止失败: {str(e)}'
        }), 500


@app.route('/api/simulation/status', methods=['GET'])
def get_simulation_status():
    """获取仿真状态"""
    try:
        status = simulation_manager.get_status()
        return jsonify(status)
    
    except Exception as e:
        return jsonify({
            'running': False,
            'error': str(e)
        }), 500


@app.route('/api/simulation/realtime', methods=['GET'])
def get_realtime_data():
    """获取实时仿真数据（路口状态、统计信息等）"""
    try:
        # 检查仿真是否运行
        if not simulation_manager.running:
            return jsonify({
                'success': False,
                'message': '仿真未运行'
            }), 200  # 返回200但success=False，避免前端报错
        
        # 获取JunctionManager实例
        junction_manager = simulation_manager.get_junction_manager()
        
        if not junction_manager:
            return jsonify({
                'success': False,
                'message': 'JunctionManager未初始化'
            }), 200  # 返回200但success=False
        
        # 获取所有路口的摘要信息
        junctions_summary = junction_manager.get_all_summaries()
        
        # 计算全局统计
        total_vehicles = sum(j.get('total_vehicles', 0) for j in junctions_summary)
        total_waiting = sum(j.get('total_halting', 0) for j in junctions_summary)
        
        # 计算平均速度（需要从所有路口获取完整数据）
        total_speed_sum = 0
        speed_count = 0
        for junction_id, junction_agent in junction_manager.get_all_junctions().items():
            if junction_agent.metrics.total_vehicles > 0:
                total_speed_sum += junction_agent.metrics.average_speed * junction_agent.metrics.total_vehicles
                speed_count += junction_agent.metrics.total_vehicles
        avg_speed = total_speed_sum / speed_count if speed_count > 0 else 0
        
        # 获取仿真状态（优先从Dashboard获取）
        dashboard_state = simulation_manager.get_dashboard_state()
        if dashboard_state:
            current_time = dashboard_state.get('simulation_time', 0)
            current_step = dashboard_state.get('current_step', 0)
            total_steps = dashboard_state.get('total_steps', 3600)
            traffic_metrics = dashboard_state.get('traffic_metrics', {})
        else:
            sim_status = simulation_manager.get_status()
            current_time = sim_status.get('current_time', 0)
            current_step = current_time
            total_steps = 3600
            traffic_metrics = {}
        
        # 调试输出（每100步输出一次）
        if current_step % 100 == 0 and current_step > 0:
            congestion_levels = [j.get('congestion_level', 0) for j in junctions_summary]
            avg_congestion = sum(congestion_levels) / len(congestion_levels) if congestion_levels else 0
            print(f"[Server] API返回数据 - Step {current_step}: "
                  f"路口数={len(junctions_summary)}, 车辆数={total_vehicles}, "
                  f"平均拥堵度={avg_congestion:.3f}")
        
        return jsonify({
            'success': True,
            'simulation': {
                'running': simulation_manager.running,
                'current_time': current_time,
                'current_step': current_step,
                'total_steps': total_steps,
                'config': simulation_manager.config or 'unknown'
            },
            'statistics': {
                'total_vehicles': total_vehicles,
                'avg_speed': round(avg_speed, 2),
                'total_waiting': total_waiting,
                'active_junctions': len(junctions_summary),
                'active_vehicles': traffic_metrics.get('active_vehicles', total_vehicles),
                'departed_step': traffic_metrics.get('departed_step', 0),
                'arrived_step': traffic_metrics.get('arrived_step', 0),
                'departed_total': traffic_metrics.get('departed_total', 0),
                'arrived_total': traffic_metrics.get('arrived_total', 0)
            },
            'junctions': junctions_summary
        })
    
    except Exception as e:
        print(f"[Server] 获取实时数据时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 200  # 返回200但success=False，避免前端频繁报错


@app.route('/api/simulation/output', methods=['GET'])
def get_simulation_output():
    """获取仿真输出日志"""
    try:
        lines = int(request.args.get('lines', 20))
        output = simulation_manager.get_recent_output(lines)
        return jsonify({
            'output': output
        })
    
    except Exception as e:
        return jsonify({
            'output': [],
            'error': str(e)
        }), 500


@app.route('/api/maps/list', methods=['GET'])
def get_available_maps():
    """获取可用的地图列表"""
    try:
        runtime_data_dir = PROJECT_ROOT / 'runtime' / 'data' / 'raw_data'
        maps = []
        
        # 扫描 raw_data 目录下的所有地图
        if runtime_data_dir.exists():
            for map_dir in runtime_data_dir.iterdir():
                if map_dir.is_dir():
                    # 检查是否包含必要的文件
                    net_file = map_dir / f'{map_dir.name}.net.xml'
                    if net_file.exists():
                        # 获取地图信息
                        map_info = {
                            'id': map_dir.name,
                            'name': _get_map_display_name(map_dir.name),
                            'description': _get_map_description(map_dir.name)
                        }
                        maps.append(map_info)
        
        # 按名称排序
        maps.sort(key=lambda x: x['id'])
        
        return jsonify({
            'success': True,
            'maps': maps,
            'current_map': config['map'].get('default_map', '81')
        })
    
    except Exception as e:
        logger.error(f"获取地图列表失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


def _get_map_display_name(map_id):
    """获取地图显示名称"""
    display_names = {
        '81': '81路口',
        'ezhou': '鄂州',
        'guanggu': '光谷',
        'output': 'Output',
        'manhattan': 'Manhattan 28x7',
        'hangzhou': 'Hangzhou',
    }
    return display_names.get(map_id, map_id.upper())


def _get_map_description(map_id):
    """获取地图描述"""
    descriptions = {
        '81': 'LibSignal 默认测试场景',
        'ezhou': 'LibSignal PPO 迁移场景',
        'guanggu': '光谷路网可视化测试场景',
        'output': '自定义导出路网场景',
        'manhattan': '纽约曼哈顿 28x7 路网',
        'hangzhou': '杭州路网',
    }
    return descriptions.get(map_id, '自定义路网')


@app.route('/api/simulation/presets', methods=['GET'])
def get_simulation_presets():
    """获取可用的仿真预设"""
    try:
        print(f"[Server] 收到获取预设请求")
        
        presets = simulation_manager.sim_config.list_presets()
        current_map = simulation_manager.sim_config.get_current_map()
        
        print(f"[Server] 预设列表: {len(presets)} 个")
        for preset in presets:
            print(f"  - {preset['name']}: {preset['description']}")
        print(f"[Server] 当前地图: {current_map}")
        
        result = {
            'presets': presets,
            'current_map': current_map
        }
        
        return jsonify(result)
    
    except Exception as e:
        print(f"[Server] 获取预设失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'presets': [],
            'error': str(e)
        }), 500


@app.route('/api/simulation/traffic-profiles', methods=['GET'])
def get_simulation_traffic_profiles():
    """获取指定地图可用的车流方案。"""
    try:
        sim_name = request.args.get('sim_name') or simulation_manager.sim_config.get_current_map()
        return jsonify({
            'success': True,
            'sim_name': sim_name,
            'profiles': simulation_manager.sim_config.list_traffic_profiles(sim_name),
        })
    except Exception as error:
        return jsonify({
            'success': False,
            'profiles': [],
            'message': str(error),
        }), 500


@app.route('/api/comparison/realtime/start', methods=['POST'])
def start_realtime_comparison():
    """同时启动隔离的 FixedTime 与 PPO 实时对比实验。"""
    if simulation_manager.running:
        return jsonify({
            'success': False,
            'message': '请先停止当前单算法仿真'
        }), 409
    try:
        data = request.get_json() or {}
        sim_name = data.get('sim_name') or simulation_manager.sim_config.get_current_map()
        traffic_profile = data.get('traffic_profile', 'default')
        gui = data.get('gui', True)
        if not isinstance(gui, bool):
            gui = str(gui).lower() not in ('false', '0', 'no', 'off')
        simlen = int(data.get('simlen', 3600))
        if simlen <= 0 or simlen > 20000:
            return jsonify({'success': False, 'message': 'simlen 必须在 1 到 20000 之间'}), 400
        # 复用受控车流白名单校验，避免 worker 启动后才报告路径错误。
        resolved_traffic = simulation_manager.sim_config.resolve_traffic_profile(sim_name, traffic_profile)
        profiles = simulation_manager.sim_config.list_traffic_profiles(sim_name)
        profile = next((item for item in profiles if item.get('id') == traffic_profile), None)
        if profile is None and traffic_profile in ('', 'default', None):
            profile = next((item for item in profiles if item.get('default')), profiles[0] if profiles else None)
        profile = profile or {'id': traffic_profile, 'name': traffic_profile, 'description': ''}
        traffic_metadata = {
            'id': traffic_profile,
            'name': profile.get('name', traffic_profile),
            'description': profile.get('description', ''),
            'flow_file': resolved_traffic.get('flow_file', ''),
        }
        result = realtime_comparison_manager.start(
            sim_name,
            traffic_profile,
            simlen,
            gui=gui,
            traffic_metadata=traffic_metadata,
        )
        return jsonify(result), (200 if result.get('success') else 409)
    except (TypeError, ValueError, FileNotFoundError) as error:
        return jsonify({'success': False, 'message': str(error)}), 400


@app.route('/api/comparison/realtime/status', methods=['GET'])
def get_realtime_comparison_status():
    return jsonify(realtime_comparison_manager.get_status())


@app.route('/api/comparison/realtime/history', methods=['GET'])
def get_realtime_comparison_live_history():
    """返回当前对比试验自启动以来的曲线序列。"""
    try:
        max_points = int(request.args.get('max_points', 600))
    except (TypeError, ValueError):
        max_points = 600
    return jsonify(realtime_comparison_manager.get_live_history(max_points))


@app.route('/api/comparison/realtime/stop', methods=['POST'])
def stop_realtime_comparison():
    return jsonify(realtime_comparison_manager.stop())


@app.route('/api/comparison/realtime/pause', methods=['POST'])
def pause_realtime_comparison():
    result = realtime_comparison_manager.pause()
    return jsonify(result), (200 if result.get('success') else 409)


@app.route('/api/comparison/realtime/resume', methods=['POST'])
def resume_realtime_comparison():
    result = realtime_comparison_manager.resume()
    return jsonify(result), (200 if result.get('success') else 409)


@app.route('/api/comparison/history', methods=['GET'])
def list_realtime_comparison_history():
    """列出已持久化的实时对比试验。"""
    try:
        limit = int(request.args.get('limit', 50))
    except (TypeError, ValueError):
        limit = 50
    return jsonify(realtime_comparison_manager.list_history(limit))


@app.route('/api/comparison/history/<session_id>', methods=['GET'])
def get_realtime_comparison_history(session_id):
    """读取一次历史试验的设置、汇总与完整时间序列。"""
    result = realtime_comparison_manager.get_history(session_id)
    return jsonify(result), (200 if result.get('success') else 404)


@app.route('/api/comparison/history/<session_id>', methods=['DELETE'])
def delete_realtime_comparison_history(session_id):
    """删除单条历史试验（后端移入本地回收目录）。"""
    result = realtime_comparison_manager.delete_history(session_id)
    return jsonify(result), (200 if result.get('success') else 404)


@app.route('/api/comparison/history/delete-bulk', methods=['POST'])
def delete_realtime_comparison_history_bulk():
    """按创建日期或实际运行步数批量删除历史试验。"""
    data = request.get_json() or {}
    mode = data.get('mode')
    value = data.get('value')
    try:
        if mode == 'before_date':
            from datetime import date
            value = str(value or '')
            date.fromisoformat(value)
        elif mode == 'shorter_than':
            value = int(value)
            if value <= 0 or value > 20000:
                raise ValueError('实际运行步数必须在 1 到 20000 之间')
        else:
            raise ValueError('请选择有效的批量删除条件')
    except (TypeError, ValueError) as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    result = realtime_comparison_manager.delete_history_bulk(mode, value)
    return jsonify(result), (200 if result.get('success') else 400)


# ========== 启动服务器 ==========

def main():
    """启动Dashboard服务器"""
    import argparse
    
    # 声明全局变量（必须在函数开始处）
    global config, MAP_DIR
    
    parser = argparse.ArgumentParser(description='SUMO交通监控Dashboard服务器')
    parser.add_argument('--host', type=str, default=config['server']['host'], 
                        help=f"监听地址（默认：{config['server']['host']}）")
    parser.add_argument('--port', type=int, default=config['server']['port'], 
                        help=f"监听端口（默认：{config['server']['port']}）")
    parser.add_argument('--debug', action='store_true', default=config['server']['debug'],
                        help='调试模式')
    parser.add_argument('--map', type=str, help='指定地图名称（如：81）')
    parser.add_argument('--config', type=str, help='指定配置文件路径')
    
    args = parser.parse_args()
    
    # 如果指定了配置文件，重新加载
    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 更新MAP_DIR
            MAP_DIR = PROJECT_ROOT / config['map']['directory']
            print(f"[Server] 使用配置文件: {config_path}")
        else:
            print(f"[Server] 警告：配置文件不存在: {config_path}，使用默认配置")
    
    print(f"[Server] 配置信息:")
    print(f"  - 地图目录: {MAP_DIR}")
    print(f"  - 默认地图: {config['map']['default_map']}")
    print(f"  - 数据文件: {config['map']['netdata_filename']}")

    if args.map:
        config.setdefault('map', {})['default_map'] = args.map
        os.environ['SUMO_MAP_NAME'] = args.map
        simulation_manager.sim_config.dashboard_config.setdefault('map', {})['default_map'] = args.map
        print(f"[Server] 已将运行时默认地图覆盖为: {args.map}")
    
    # 预加载地图
    if args.map:
        try:
            network_data = load_named_network_data(args.map)
            junction_manager.initialize_from_network_data(network_data)
        except Exception as e:
            print(f"[Server] 警告：指定地图加载失败: {args.map} ({e})")
            print(f"[Server] 尝试加载默认地图...")
            default_data = load_default_network_data()
            if default_data:
                junction_manager.initialize_from_network_data(default_data)
    else:
        # 加载默认地图
        default_data = load_default_network_data()
        if default_data:
            junction_manager.initialize_from_network_data(default_data)
    
    # 初始化工具控制器
    global data_controller, models_controller, comparison_controller
    
    # 从配置文件读取TDengine配置
    tdengine_config = config.get('tdengine', {})
    tdengine_host = tdengine_config.get('host', 'localhost')
    tdengine_port = tdengine_config.get('port', 6060)
    data_controller = get_data_controller()(tdengine_host, tdengine_port)
    
    models_controller = get_models_controller()()
    comparison_controller = get_comparison_controller()()
    
    print(f"\n[Server] ====================================")
    print(f"[Server] Dashboard服务器启动")
    print(f"[Server] 访问地址: http://{args.host}:{args.port}")
    print(f"[Server] 路口数量: {len(junction_manager.junctions)}")
    print(f"[Server] ====================================")
    print(f"[Server] 按 Ctrl+C 停止服务器\n")

    configure_http_request_logging(args.debug)
    app.run(host=args.host, port=args.port, debug=args.debug)


# ========== 工具模块API路由 ==========

# 交通数据相关
@app.route('/api/tools/data/query', methods=['POST'])
def query_traffic_data():
    """查询交通数据"""
    try:
        query_params = request.json
        result = data_controller.query_data(query_params)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/data/analyze', methods=['POST'])
def analyze_traffic_data():
    """分析交通数据"""
    try:
        analysis_params = request.json
        result = data_controller.analyze_data(analysis_params)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/data/export', methods=['POST'])
def export_traffic_data():
    """导出交通数据"""
    try:
        export_params = request.json
        result = data_controller.export_data(export_params)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/data/statistics', methods=['GET'])
def get_data_statistics():
    """获取数据统计信息"""
    try:
        statistics = data_controller.get_data_statistics()
        return jsonify({'success': True, 'statistics': statistics})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/data/tdengine-config', methods=['GET'])
def get_tdengine_config():
    """获取TDengine配置"""
    try:
        config = data_controller.get_tdengine_config()
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# 模型管理相关
@app.route('/api/tools/models/list', methods=['GET'])
def list_models():
    """列出所有模型"""
    try:
        filters = request.args.to_dict()
        result = models_controller.list_models(filters)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/models/load', methods=['POST'])
def load_model():
    """加载模型"""
    try:
        model_id = request.json.get('model_id')
        result = models_controller.load_model(model_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/models/delete', methods=['POST'])
def delete_model():
    """删除模型"""
    try:
        model_id = request.json.get('model_id')
        result = models_controller.delete_model(model_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/models/info/<path:model_id>', methods=['GET'])
def get_model_info(model_id):
    """获取模型信息"""
    try:
        # Flask会自动URL解码
        result = models_controller.get_model_info(model_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/models/evaluate', methods=['POST'])
def evaluate_model():
    """评估模型"""
    try:
        model_id = request.json.get('model_id')
        eval_params = request.json.get('params', {})
        result = models_controller.evaluate_model(model_id, eval_params)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/models/file/<path:model_id>/<file_type>', methods=['GET'])
def get_model_file(model_id, file_type):
    """获取模型文件"""
    try:
        result = models_controller.get_model_file(model_id, file_type)
        if result['success']:
            file_path = result['file_path']
            if file_type == 'params':
                # 返回JSON内容
                import json
                with open(file_path, 'r') as f:
                    content = json.load(f)
                return jsonify({'success': True, 'content': content})
            elif file_type == 'metrics':
                # 返回图片文件
                from flask import send_file
                return send_file(file_path, mimetype='image/png')
        else:
            return jsonify(result), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== 对比实验相关 ====================

@app.route('/api/tools/comparison/start', methods=['POST'])
def start_comparison_experiment():
    """启动对比实验（创建并运行）"""
    try:
        config = request.json
        # 创建实验
        create_result = comparison_controller.create_experiment(config)
        if not create_result.get('success'):
            return jsonify(create_result), 500
        
        experiment_id = create_result.get('experiment_id')
        
        # 立即运行实验
        run_result = comparison_controller.run_experiment(experiment_id)
        if run_result.get('success'):
            return jsonify({
                'success': True,
                'message': '对比实验已启动',
                'experiment_id': experiment_id
            })
        else:
            return jsonify(run_result), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/create', methods=['POST'])
def create_experiment():
    """创建对比实验"""
    try:
        experiment_config = request.json
        result = comparison_controller.create_experiment(experiment_config)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/run', methods=['POST'])
def run_experiment():
    """运行对比实验"""
    try:
        experiment_id = request.json.get('experiment_id')
        result = comparison_controller.run_experiment(experiment_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/stop', methods=['POST'])
def stop_experiment():
    """停止对比实验"""
    try:
        experiment_id = request.json.get('experiment_id')
        result = comparison_controller.stop_experiment(experiment_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/status/<experiment_id>', methods=['GET'])
def get_experiment_status(experiment_id):
    """获取实验状态"""
    try:
        result = comparison_controller.get_experiment_status(experiment_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/results/<experiment_id>', methods=['GET'])
def get_experiment_results(experiment_id):
    """获取实验结果"""
    try:
        result = comparison_controller.get_experiment_results(experiment_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/chart/<path:filename>', methods=['GET'])
def get_experiment_chart(filename):
    """获取实验图表文件"""
    try:
        experiments_dir = DASHBOARD_ROOT / 'experiments'
        return send_from_directory(experiments_dir, filename)
    except Exception as e:
        logger.error(f"获取图表文件失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 404


@app.route('/api/tools/comparison/list', methods=['GET'])
def list_experiments():
    """列出所有实验"""
    try:
        result = comparison_controller.list_experiments()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/logs', methods=['GET'])
def get_comparison_logs():
    """获取对比实验日志"""
    try:
        limit = request.args.get('limit', 50, type=int)
        result = comparison_controller.get_experiment_logs(limit)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/export/<experiment_id>', methods=['GET'])
def export_comparison_results(experiment_id):
    """导出实验结果"""
    try:
        result = comparison_controller.export_results(experiment_id)
        if result.get('success'):
            file_path = result.get('file_path')
            return send_from_directory(
                os.path.dirname(file_path),
                os.path.basename(file_path),
                as_attachment=True
            )
        else:
            return jsonify(result), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tools/comparison/report', methods=['POST'])
def generate_experiment_report():
    """生成实验报告"""
    try:
        experiment_id = request.json.get('experiment_id')
        report_format = request.json.get('format', 'html')
        result = comparison_controller.generate_report(experiment_id, report_format)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    main()
