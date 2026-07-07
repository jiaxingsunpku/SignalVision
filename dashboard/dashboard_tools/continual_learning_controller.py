"""
持续学习控制器
负责管理模型的持续评估、迭代与结果沉淀
"""

import os
import sys
import logging
import subprocess
import threading
import json
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入配置转换器（使用相对路径）
adapter_path = PROJECT_ROOT / 'adapter'
sys.path.insert(0, str(adapter_path))
from config_converter import ConfigConverter

logger = logging.getLogger(__name__)


class ComparisonController:
    """
    持续学习控制器
    管理持续学习相关功能，包括：
    - 创建持续学习任务
    - 运行多个模型评估
    - 收集和分析结果数据
    - 生成分析报告
    """
    
    def __init__(self):
        """初始化持续学习控制器"""
        self.experiments = {}
        self.current_experiment = None
        self.is_running = False
        self.experiment_process = None
        self.experiment_logs = []
        logger.info("持续学习控制器初始化完成")
    
    def create_experiment(self, experiment_config):
        """
        创建新的对比实验
        
        Args:
            experiment_config (dict): 实验配置
                - name: 实验名称
                - description: 实验描述
                - scenario: 测试场景
                - demand: 交通需求
                - sim_length: 仿真时长
                - traffic_scale: 交通规模
                - models: 参与对比的训练模型列表 [{"id": "...", "epoch": 130}, ...]
                - baselines: 基准算法列表 ["fixedtime", "maxpressure"]
                - metrics: 评估指标列表
        
        Returns:
            dict: 创建结果
        """
        try:
            logger.info(f"创建对比实验: {experiment_config.get('name')}")
            
            # 验证配置
            if not experiment_config.get('name'):
                return {'success': False, 'message': '实验名称不能为空'}
            
            # 检查是否至少选择了一个模型或基准算法
            models = experiment_config.get('models', [])
            baselines = experiment_config.get('baselines', [])
            if not models and not baselines:
                return {'success': False, 'message': '请至少选择一个模型或基准算法'}
            
            # 生成实验ID
            experiment_id = f"{experiment_config['name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 创建实验目录
            exp_dir = PROJECT_ROOT / 'dashboard' / 'experiments' / experiment_id
            exp_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存实验配置
            config_file = exp_dir / 'config.json'
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(experiment_config, f, indent=2, ensure_ascii=False)
            
            # 初始化实验状态
            self.experiments[experiment_id] = {
                'config': experiment_config,
                'status': 'created',
                'progress': 0,
                'total_tasks': len(models) + len(baselines),
                'completed_tasks': 0,
                'results': {},
                'exp_dir': str(exp_dir),
                'created_at': datetime.now().isoformat()
            }
            
            logger.info(f"实验创建成功: {experiment_id}")
            return {
                'success': True,
                'experiment_id': experiment_id,
                'message': '实验创建成功'
            }
            
        except Exception as e:
            logger.error(f"创建实验失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'创建失败: {str(e)}'
            }
    
    def run_experiment(self, experiment_id):
        """
        运行对比实验
        
        Args:
            experiment_id (str): 实验ID
        
        Returns:
            dict: 运行结果
        """
        try:
            logger.info(f"运行对比实验: {experiment_id}")
            
            if experiment_id not in self.experiments:
                return {'success': False, 'message': '实验不存在'}
            
            if self.is_running:
                return {'success': False, 'message': '已有实验正在运行'}
            
            # 更新状态
            self.experiments[experiment_id]['status'] = 'running'
            self.current_experiment = experiment_id
            self.is_running = True
            self.experiment_logs = []
            
            # 在后台线程中运行实验
            thread = threading.Thread(target=self._run_experiment_thread, args=(experiment_id,))
            thread.daemon = True
            thread.start()
            
            return {
                'success': True,
                'message': '实验启动成功'
            }
            
        except Exception as e:
            logger.error(f"运行实验失败: {str(e)}", exc_info=True)
            self.is_running = False
            return {
                'success': False,
                'message': f'运行失败: {str(e)}'
            }
    
    def _run_experiment_thread(self, experiment_id):
        """在后台线程中运行实验（并行执行）"""
        try:
            exp = self.experiments[experiment_id]
            config = exp['config']
            exp_dir = Path(exp['exp_dir'])
            
            self._add_log('info', f'开始运行实验: {config["name"]}')
            
            # 准备测试配置
            scenario = config.get('scenario', '81')
            demand = config.get('demand', 'onfly')
            sim_length = config.get('sim_length', 3600)
            traffic_scale = config.get('traffic_scale', 1.0)
            
            # 准备所有测试任务
            test_tasks = []
            
            # 1. 添加基准算法任务
            baselines = config.get('baselines', [])
            for baseline in baselines:
                test_tasks.append({
                    'type': 'baseline',
                    'name': baseline,
                    'algorithm': baseline,
                    'params': (baseline, scenario, demand, sim_length, traffic_scale, exp_dir)
                })
            
            # 2. 添加训练模型任务
            models = config.get('models', [])
            for model in models:
                model_id = model['id']
                epoch = model.get('epoch')
                result_key = f"{model_id}_epoch{epoch}"
                test_tasks.append({
                    'type': 'model',
                    'name': f"{model_id} (Epoch {epoch})",
                    'result_key': result_key,
                    'params': (model_id, epoch, scenario, demand, sim_length, traffic_scale, exp_dir)
                })
            
            # 使用线程池并行执行测试（最多同时运行3个任务，避免资源竞争）
            max_workers = min(3, len(test_tasks))
            self._add_log('info', f'使用 {max_workers} 个并行工作线程执行 {len(test_tasks)} 个测试任务')
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_task = {}
                for task in test_tasks:
                    if task['type'] == 'baseline':
                        future = executor.submit(self._run_baseline, *task['params'])
                    else:  # model
                        future = executor.submit(self._run_model, *task['params'])
                    future_to_task[future] = task
                    self._add_log('info', f'已提交任务: {task["name"]}')
                
                # 收集结果
                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        result = future.result()
                        
                        # 保存结果
                        if task['type'] == 'baseline':
                            exp['results'][task['algorithm']] = result
                        else:
                            exp['results'][task['result_key']] = result
                        
                        # 更新进度
                        exp['completed_tasks'] += 1
                        exp['progress'] = int((exp['completed_tasks'] / exp['total_tasks']) * 100)
                        
                        # 记录日志
                        status = '成功' if result.get('success') else '失败'
                        log_level = 'success' if result.get('success') else 'error'
                        self._add_log(log_level, f'{task["name"]} 测试{status}')
                        
                    except Exception as e:
                        logger.error(f"任务 {task['name']} 执行失败: {e}", exc_info=True)
                        self._add_log('error', f'{task["name"]} 测试异常: {str(e)}')
            
            # 3. 生成对比报告
            self._add_log('info', '生成对比报告...')
            self._generate_comparison_report(experiment_id)
            
            # 更新状态
            exp['status'] = 'completed'
            exp['progress'] = 100
            self._add_log('success', '实验完成！')
            
        except Exception as e:
            logger.error(f"实验运行异常: {e}", exc_info=True)
            self.experiments[experiment_id]['status'] = 'failed'
            self._add_log('error', f'实验失败: {str(e)}')
        finally:
            self.is_running = False
            self.current_experiment = None
    
    def _run_baseline(self, algorithm, scenario, demand, sim_length, traffic_scale, exp_dir):
        """运行基准算法"""
        try:
            # 临时修改agent配置文件以设置test_steps
            runtime_dir = PROJECT_ROOT / 'runtime'
            agent_name = ConfigConverter.ALGORITHM_MAPPING.get(algorithm, algorithm)
            world_name = 'sumo'
            network_name = ConfigConverter.resolve_network(scenario, world_name)
            
            # 备份并修改配置文件
            self._modify_agent_config_for_test(agent_name, sim_length)
            
            args = [
                sys.executable,
                str(runtime_dir / 'run.py'),
                '--task', 'tsc',
                '--agent', agent_name,
                '--world', world_name,
                '--network', network_name,
                '--dataset', demand,
                '--prefix', f'comparison_{algorithm}',
                '--interface', 'libsumo',
                '--thread_num', '1',
            ]
            
            # 运行测试
            self._add_log('output', f'Python: {sys.executable}')
            self._add_log('output', f'执行命令: {" ".join(args)}')
            
            # 确保使用正确的环境
            env = os.environ.copy()
            
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                cwd=str(runtime_dir),
                env=env
            )
            
            # 读取输出
            output_lines = []
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if line:
                    output_lines.append(line)
                    self._add_log('output', f'[{algorithm}] {line}')
            
            return_code = process.wait()
            
            # 恢复配置文件
            self._restore_agent_config(agent_name)
            
            # 保存完整输出到日志文件
            output_log_file = exp_dir / f'{algorithm}_output.log'
            with open(output_log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(output_lines))
            logger.info(f"输出已保存到: {output_log_file}")
            
            # 解析结果
            result = self._parse_test_output(output_lines, algorithm)
            result['return_code'] = return_code
            result['algorithm'] = algorithm
            result['output_file'] = str(output_log_file)
            
            return result
            
        except Exception as e:
            logger.error(f"运行基准算法失败 {algorithm}: {e}", exc_info=True)
            # 确保恢复配置
            try:
                self._restore_agent_config(agent_name)
            except:
                pass
            return {'success': False, 'error': str(e), 'algorithm': algorithm}
    
    def _run_model(self, model_id, epoch, scenario, demand, sim_length, traffic_scale, exp_dir):
        """运行训练模型"""
        try:
            # 解析模型路径
            # model_id 格式: "algorithm/network/model_name"
            parts = model_id.split('/')
            if len(parts) != 3:
                raise ValueError(f'Invalid model_id: {model_id}')
            
            algorithm, network, model_name = parts
            agent_name = ConfigConverter.ALGORITHM_MAPPING.get(algorithm, 'colight_pytorch_agent')
            world_name = 'sumo'
            network_name = ConfigConverter.resolve_network(scenario, world_name)
            
            # 找到模型目录
            runtime_dir = PROJECT_ROOT / 'runtime'
            model_dir = runtime_dir / 'data' / 'output_data' / 'tsc'
            
            # 查找agent目录
            agent_dir = None
            for d in model_dir.iterdir():
                if d.is_dir() and algorithm in d.name:
                    agent_dir = d
                    break
            
            if not agent_dir:
                raise ValueError(f'Agent directory not found for algorithm: {algorithm}')
            
            model_path = agent_dir / network / model_name
            
            if not model_path.exists():
                raise ValueError(f'Model directory not found: {model_path}')
            
            # 检查模型文件是否存在
            model_files_dir = model_path / 'model'
            if not model_files_dir.exists() or not list(model_files_dir.glob('*.pt')):
                raise ValueError(f'No model files found in: {model_files_dir}')
            
            # 处理 epoch 参数
            if epoch == 'N/A' or epoch == 'latest':
                # 查找最新的 epoch
                model_files = list(model_files_dir.glob('*.pt'))
                epochs = []
                for mf in model_files:
                    try:
                        epoch_num = int(mf.stem.split('_')[0])
                        epochs.append(epoch_num)
                    except:
                        pass
                if epochs:
                    epoch = max(epochs)
                    logger.info(f"使用最新的 epoch: {epoch}")
                else:
                    raise ValueError(f'No valid epoch found in model files')
            
            # 备份并修改配置文件，添加模型加载参数
            self._modify_agent_config_for_test(agent_name, sim_length, load_model=True, load_episode=int(epoch))
            
            # 构建测试命令
            # 注意：prefix必须与模型目录名一致，LibSignal会在该目录下查找模型
            args = [
                sys.executable,
                str(runtime_dir / 'run.py'),
                '--task', 'tsc',
                '--agent', agent_name,
                '--world', world_name,
                '--network', network_name,
                '--dataset', demand,
                '--prefix', model_name,  # 使用模型目录名作为prefix
                '--interface', 'libsumo',
                '--thread_num', '1',
            ]
            
            # 运行测试
            self._add_log('output', f'Python: {sys.executable}')
            self._add_log('output', f'执行命令: {" ".join(args)}')
            
            # 确保使用正确的环境
            env = os.environ.copy()
            
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                cwd=str(runtime_dir),
                env=env
            )
            
            # 读取输出
            output_lines = []
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if line:
                    output_lines.append(line)
                    self._add_log('output', f'[{model_name}] {line}')
            
            return_code = process.wait()
            
            # 恢复配置文件
            self._restore_agent_config(agent_name)
            
            # 保存完整输出到日志文件
            output_log_file = exp_dir / f'{model_name}_epoch{epoch}_output.log'
            with open(output_log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(output_lines))
            logger.info(f"输出已保存到: {output_log_file}")
            
            # 解析结果
            result = self._parse_test_output(output_lines, model_name)
            result['return_code'] = return_code
            result['model_id'] = model_id
            result['epoch'] = epoch
            result['output_file'] = str(output_log_file)
            
            return result
            
        except Exception as e:
            logger.error(f"运行模型失败 {model_id}: {e}", exc_info=True)
            # 确保恢复配置
            try:
                agent_name = ConfigConverter.ALGORITHM_MAPPING.get(model_id.split('/')[0], 'colight_pytorch_agent')
                self._restore_agent_config(agent_name)
            except:
                pass
            return {'success': False, 'error': str(e), 'model_id': model_id}
    
    def _parse_test_output(self, output_lines, name):
        """解析测试输出，提取性能指标
        
        LibSignal 的实际输出格式:
        "Final Travel Time is 233.4567, mean rewards: -123.45, queue: 45.67, delay: 123.45, throughput: 1234"
        """
        result = {
            'name': name,
            'travel_time': None,
            'queue_length': None,
            'delay': None,
            'throughput': None,
            'success': False
        }
        
        try:
            logger.info(f"开始解析 {name} 的输出，共 {len(output_lines)} 行")
            
            for line in output_lines:
                # LibSignal 的输出格式: "Final Travel Time is X, mean rewards: Y, queue: Z, delay: W, throughput: T"
                if 'Final Travel Time is' in line or 'final travel time is' in line.lower():
                    logger.info(f"找到测试结果行: {line}")
                    
                    # 提取 Travel Time
                    match = re.search(r'(?:Final\s+)?Travel\s+Time\s+is\s+(\d+\.?\d*)', line, re.IGNORECASE)
                    if match:
                        result['travel_time'] = float(match.group(1))
                        logger.info(f"  travel_time: {result['travel_time']}")
                    
                    # 提取 Queue
                    match = re.search(r'queue:\s*(\d+\.?\d*)', line, re.IGNORECASE)
                    if match:
                        result['queue_length'] = float(match.group(1))
                        logger.info(f"  queue_length: {result['queue_length']}")
                    
                    # 提取 Delay
                    match = re.search(r'delay:\s*(\d+\.?\d*)', line, re.IGNORECASE)
                    if match:
                        result['delay'] = float(match.group(1))
                        logger.info(f"  delay: {result['delay']}")
                    
                    # 提取 Throughput
                    match = re.search(r'throughput:\s*(\d+)', line, re.IGNORECASE)
                    if match:
                        result['throughput'] = int(match.group(1))
                        logger.info(f"  throughput: {result['throughput']}")
                    
                    # 找到结果行，标记为成功
                    result['success'] = True
                    break
            
            # 如果没找到，输出最后20行用于调试
            if not result['success']:
                logger.warning(f"{name} 未找到测试结果")
                if output_lines:
                    logger.warning(f"最后20行输出:")
                    for line in output_lines[-20:]:
                        logger.warning(f"  {line}")
            else:
                logger.info(f"{name} 解析成功")
            
        except Exception as e:
            logger.error(f"解析输出失败: {e}", exc_info=True)
        
        return result
    
    def _generate_comparison_report(self, experiment_id):
        """生成对比报告"""
        try:
            exp = self.experiments[experiment_id]
            exp_dir = Path(exp['exp_dir'])
            results = exp['results']
            
            # 保存原始结果
            results_file = exp_dir / 'results.json'
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            # 生成对比图表
            chart_files = self._generate_comparison_charts(exp_dir, results)
            
            # 生成HTML报告（包含图表）
            html_file = exp_dir / 'report.html'
            html_content = self._generate_html_report(exp, chart_files)
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"对比报告已生成: {html_file}")
            
        except Exception as e:
            logger.error(f"生成报告失败: {e}", exc_info=True)
    
    def _generate_comparison_charts(self, exp_dir, results):
        """生成对比图表（travel_time 和 throughput）"""
        import matplotlib
        matplotlib.use('Agg')  # 使用非交互式后端
        import matplotlib.pyplot as plt
        
        chart_files = {}
        
        try:
            # 提取成功的结果
            successful_results = {name: result for name, result in results.items() if result.get('success')}
            
            if not successful_results:
                logger.warning("没有成功的测试结果，跳过图表生成")
                return chart_files
            
            # 准备数据
            names = []
            travel_times = []
            throughputs = []
            
            for name, result in successful_results.items():
                # 简化显示名称
                display_name = name.replace('colight/manhattan/', '').replace('_epoch', ' E')
                names.append(display_name)
                travel_times.append(result.get('travel_time', 0))
                throughputs.append(result.get('throughput', 0))
            
            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 创建双柱状图
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
            
            # 图1: 平均行程时间（越低越好）
            colors1 = ['#FF6B6B' if tt == max(travel_times) else '#4ECDC4' if tt == min(travel_times) else '#95E1D3' 
                       for tt in travel_times]
            bars1 = ax1.bar(names, travel_times, color=colors1, edgecolor='black', linewidth=1.2)
            ax1.set_xlabel('Algorithm/Model', fontsize=12, fontweight='bold')
            ax1.set_ylabel('Average Travel Time (s)', fontsize=12, fontweight='bold')
            ax1.set_title('Average Travel Time Comparison\n(Lower is Better)', fontsize=14, fontweight='bold', pad=15)
            ax1.grid(axis='y', alpha=0.3, linestyle='--')
            
            # 在柱子上方添加数值标签
            for bar, val in zip(bars1, travel_times):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height,
                        f'{val:.2f}',
                        ha='center', va='bottom', fontsize=10, fontweight='bold')
            
            # 图2: 通行量（越高越好）
            colors2 = ['#FF6B6B' if tp == min(throughputs) else '#4ECDC4' if tp == max(throughputs) else '#95E1D3' 
                       for tp in throughputs]
            bars2 = ax2.bar(names, throughputs, color=colors2, edgecolor='black', linewidth=1.2)
            ax2.set_xlabel('Algorithm/Model', fontsize=12, fontweight='bold')
            ax2.set_ylabel('Throughput (vehicles)', fontsize=12, fontweight='bold')
            ax2.set_title('Throughput Comparison\n(Higher is Better)', fontsize=14, fontweight='bold', pad=15)
            ax2.grid(axis='y', alpha=0.3, linestyle='--')
            
            # 在柱子上方添加数值标签
            for bar, val in zip(bars2, throughputs):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(val)}',
                        ha='center', va='bottom', fontsize=10, fontweight='bold')
            
            # 调整布局
            plt.tight_layout()
            
            # 保存图表
            chart_path = exp_dir / 'comparison_chart.png'
            plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            
            chart_files['comparison_chart'] = chart_path.name
            logger.info(f"对比图表已生成: {chart_path}")
            
        except Exception as e:
            logger.error(f"生成图表失败: {e}", exc_info=True)
        
        return chart_files
    
    def _generate_html_report(self, exp, chart_files=None):
        """生成HTML格式的对比报告"""
        config = exp['config']
        results = exp['results']
        
        # 构建结果表格
        table_rows = []
        for name, result in results.items():
            if result.get('success'):
                table_rows.append(f"""
                <tr>
                    <td>{name}</td>
                    <td>{result.get('travel_time', 'N/A')}</td>
                    <td>{result.get('queue_length', 'N/A')}</td>
                    <td>{result.get('delay', 'N/A')}</td>
                    <td>{result.get('throughput', 'N/A')}</td>
                </tr>
                """)
        
        # 图表HTML
        chart_html = ""
        if chart_files and 'comparison_chart' in chart_files:
            chart_html = f"""
            <h2>性能对比图表</h2>
            <div style="text-align: center; margin: 30px 0;">
                <img src="{chart_files['comparison_chart']}" alt="对比图表" style="max-width: 100%; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>对比实验报告 - {config['name']}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
                h2 {{ color: #555; margin-top: 30px; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                tr:hover {{ background-color: #f0f0f0; }}
                .info {{ margin: 10px 0; background-color: #f9f9f9; padding: 15px; border-radius: 5px; }}
                .info p {{ margin: 5px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚦 对比实验报告</h1>
                <div class="info">
                    <p><strong>实验名称:</strong> {config['name']}</p>
                    <p><strong>实验描述:</strong> {config.get('description', 'N/A')}</p>
                    <p><strong>测试场景:</strong> {config.get('scenario', 'N/A')}</p>
                    <p><strong>交通需求:</strong> {config.get('demand', 'N/A')}</p>
                    <p><strong>仿真时长:</strong> {config.get('sim_length', 'N/A')} 步</p>
                    <p><strong>完成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                {chart_html}
                
                <h2>📊 详细数据</h2>
                <table>
                    <tr>
                        <th>算法/模型</th>
                        <th>平均行程时间 (s)</th>
                        <th>队列长度</th>
                        <th>延迟 (s)</th>
                        <th>通行量</th>
                    </tr>
                    {''.join(table_rows)}
                </table>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _modify_agent_config_for_test(self, agent_name, test_steps, load_model=False, load_episode=None):
        """
        临时修改agent配置文件以设置测试参数
        
        Args:
            agent_name: agent名称
            test_steps: 测试步数
            load_model: 是否加载模型
            load_episode: 加载的epoch编号
        """
        try:
            import yaml
            import shutil
            
            runtime_dir = PROJECT_ROOT / 'runtime'
            config_path = runtime_dir / 'configs' / 'tsc' / f'{agent_name}.yml'
            backup_path = runtime_dir / 'configs' / 'tsc' / f'{agent_name}.yml.comparison_backup'
            
            if not config_path.exists():
                logger.warning(f"配置文件不存在: {config_path}")
                return
            
            # 创建备份（如果还没有）
            if not backup_path.exists():
                shutil.copy2(config_path, backup_path)
                logger.info(f"已创建配置备份: {backup_path}")
            else:
                # 从备份恢复
                shutil.copy2(backup_path, config_path)
                logger.info(f"已从备份恢复配置: {config_path}")
            
            # 读取配置
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            # 修改test_steps
            if 'trainer' not in config:
                config['trainer'] = {}
            config['trainer']['test_steps'] = test_steps
            
            # 如果需要加载模型，添加模型加载参数
            if load_model and load_episode is not None:
                if 'model' not in config:
                    config['model'] = {}
                config['model']['load_model'] = True
                config['model']['test_model'] = True
                config['model']['train_model'] = False
                
                if 'trainer' not in config:
                    config['trainer'] = {}
                config['trainer']['episodes'] = load_episode
                
                logger.info(f"已设置 {agent_name} 加载模型: epoch={load_episode}")
            
            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"已设置 {agent_name} 的 test_steps = {test_steps}")
            
        except Exception as e:
            logger.error(f"修改配置文件失败: {e}", exc_info=True)
    
    def _restore_agent_config(self, agent_name):
        """恢复agent配置文件"""
        try:
            import shutil
            
            runtime_dir = PROJECT_ROOT / 'runtime'
            config_path = runtime_dir / 'configs' / 'tsc' / f'{agent_name}.yml'
            backup_path = runtime_dir / 'configs' / 'tsc' / f'{agent_name}.yml.comparison_backup'
            
            if backup_path.exists():
                shutil.copy2(backup_path, config_path)
                logger.info(f"已恢复配置: {config_path}")
        except Exception as e:
            logger.error(f"恢复配置文件失败: {e}", exc_info=True)
    
    def _add_log(self, level, message):
        """添加日志"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message
        }
        self.experiment_logs.append(log_entry)
        logger.info(f'[Comparison] [{level}] {message}')
    
    def stop_experiment(self, experiment_id):
        """
        停止正在运行的实验
        
        Args:
            experiment_id (str): 实验ID
        
        Returns:
            dict: 停止结果
        """
        try:
            logger.info(f"停止实验: {experiment_id}")
            
            if experiment_id not in self.experiments:
                return {'success': False, 'message': '实验不存在'}
            
            if self.experiment_process:
                self.experiment_process.terminate()
                self.experiment_process.wait()
                self.experiment_process = None
            
            self.experiments[experiment_id]['status'] = 'stopped'
            self.is_running = False
            self._add_log('warning', '实验已被用户停止')
            
            return {
                'success': True,
                'message': '实验已停止'
            }
            
        except Exception as e:
            logger.error(f"停止实验失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'停止失败: {str(e)}'
            }
    
    def get_experiment_status(self, experiment_id=None):
        """
        获取实验状态
        
        Args:
            experiment_id (str, optional): 实验ID，如果为None则返回当前实验状态
        
        Returns:
            dict: 实验状态
        """
        if experiment_id is None:
            experiment_id = self.current_experiment
        
        if not experiment_id or experiment_id not in self.experiments:
            return {
                'success': False,
                'message': '实验不存在',
                'is_running': False
            }
        
        exp = self.experiments[experiment_id]
        
        # 构建模型状态字典
        models_status = {}
        config = exp.get('config', {})
        results = exp.get('results', {})
        
        # 为每个模型和基准算法添加状态
        for model in config.get('models', []):
            model_id = model['id']
            result_key = f"{model_id}_epoch{model.get('epoch', 'latest')}"
            if result_key in results:
                models_status[model_id] = {
                    'status': '已完成',
                    'progress': 100
                }
            else:
                models_status[model_id] = {
                    'status': '等待中' if exp['status'] == 'created' else '运行中',
                    'progress': 0 if exp['status'] == 'created' else 50
                }
        
        for baseline in config.get('baselines', []):
            if baseline in results:
                models_status[baseline] = {
                    'status': '已完成',
                    'progress': 100
                }
            else:
                models_status[baseline] = {
                    'status': '等待中' if exp['status'] == 'created' else '运行中',
                    'progress': 0 if exp['status'] == 'created' else 50
                }
        
        return {
            'success': True,
            'is_running': exp['status'] == 'running',
            'status': exp['status'],
            'progress': exp.get('progress', 0),
            'overall_progress': exp.get('progress', 0),  # 添加前端期望的字段
            'completed_tasks': exp.get('completed_tasks', 0),
            'total_tasks': exp.get('total_tasks', 0),
            'models_status': models_status,  # 添加模型状态
            'is_completed': exp['status'] in ['completed', 'stopped', 'failed']  # 添加完成标志
        }
    
    def get_experiment_logs(self, limit=50):
        """
        获取实验日志
        
        Args:
            limit (int): 返回的日志条数
        
        Returns:
            dict: 日志数据
        """
        return {
            'success': True,
            'logs': self.experiment_logs[-limit:] if limit else self.experiment_logs
        }
    
    def get_experiment_results(self, experiment_id):
        """
        获取实验结果
        
        Args:
            experiment_id (str): 实验ID
        
        Returns:
            dict: 实验结果
        """
        try:
            if experiment_id not in self.experiments:
                return {'success': False, 'message': '实验不存在'}
            
            exp = self.experiments[experiment_id]
            results = exp.get('results', {})
            exp_dir = Path(exp.get('exp_dir', ''))
            
            # 计算统计信息
            analysis = self._analyze_results(results)
            
            # 查找图表文件
            chart_file = None
            if exp_dir.exists():
                chart_path = exp_dir / 'comparison_chart.png'
                if chart_path.exists():
                    # 返回相对于 experiments 目录的路径
                    chart_file = f"{exp_dir.name}/comparison_chart.png"
            
            return {
                'success': True,
                'results': results,
                'analysis': analysis,
                'chart_file': chart_file
            }
            
        except Exception as e:
            logger.error(f"获取实验结果失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }
    
    def _analyze_results(self, results):
        """分析实验结果"""
        analysis = {
            'best_travel_time': None,
            'best_queue': None,
            'best_delay': None,
            'best_throughput': None
        }
        
        try:
            # 找出各项指标最优的模型
            valid_results = {k: v for k, v in results.items() if v.get('success')}
            
            if valid_results:
                # 平均行程时间（越小越好）
                travel_times = {k: v['travel_time'] for k, v in valid_results.items() if v.get('travel_time') is not None}
                if travel_times:
                    analysis['best_travel_time'] = min(travel_times, key=travel_times.get)
                
                # 队列长度（越小越好）
                queues = {k: v['queue_length'] for k, v in valid_results.items() if v.get('queue_length') is not None}
                if queues:
                    analysis['best_queue'] = min(queues, key=queues.get)
                
                # 延迟（越小越好）
                delays = {k: v['delay'] for k, v in valid_results.items() if v.get('delay') is not None}
                if delays:
                    analysis['best_delay'] = min(delays, key=delays.get)
                
                # 通行量（越大越好）
                throughputs = {k: v['throughput'] for k, v in valid_results.items() if v.get('throughput') is not None}
                if throughputs:
                    analysis['best_throughput'] = max(throughputs, key=throughputs.get)
        
        except Exception as e:
            logger.warning(f"分析结果失败: {e}")
        
        return analysis
    
    def list_experiments(self):
        """
        列出所有实验
        
        Returns:
            dict: 实验列表
        """
        return {
            'success': True,
            'experiments': [
                {
                    'id': exp_id,
                    'name': exp_data['config'].get('name', ''),
                    'status': exp_data['status'],
                    'created_at': exp_data.get('created_at', ''),
                    'progress': exp_data.get('progress', 0)
                }
                for exp_id, exp_data in self.experiments.items()
            ]
        }
    
    def export_results(self, experiment_id):
        """
        导出实验结果
        
        Args:
            experiment_id (str): 实验ID
        
        Returns:
            dict: 导出结果
        """
        try:
            logger.info(f"导出实验结果: {experiment_id}")
            
            if experiment_id not in self.experiments:
                return {'success': False, 'message': '实验不存在'}
            
            exp = self.experiments[experiment_id]
            exp_dir = Path(exp['exp_dir'])
            
            # 导出JSON格式的结果
            export_file = exp_dir / f'{experiment_id}_export.json'
            export_data = {
                'experiment_id': experiment_id,
                'config': exp['config'],
                'results': exp['results'],
                'status': exp['status'],
                'created_at': exp.get('created_at', ''),
                'completed_at': datetime.now().isoformat() if exp['status'] == 'completed' else None
            }
            
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            return {
                'success': True,
                'file_path': str(export_file),
                'message': '结果导出成功'
            }
            
        except Exception as e:
            logger.error(f"导出结果失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'导出失败: {str(e)}'
        }
    
    def generate_report(self, experiment_id, report_format='html'):
        """
        生成实验对比报告
        
        Args:
            experiment_id (str): 实验ID
            report_format (str): 报告格式 (html, json)
        
        Returns:
            dict: 报告生成结果
        """
        try:
            logger.info(f"生成实验报告: {experiment_id}, 格式: {report_format}")
            
            if experiment_id not in self.experiments:
                return {'success': False, 'message': '实验不存在'}
            
            exp = self.experiments[experiment_id]
            exp_dir = Path(exp['exp_dir'])
            
            if report_format == 'html':
                report_file = exp_dir / 'report.html'
                html_content = self._generate_html_report(exp)
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                return {
                    'success': True,
                    'report_path': str(report_file),
                    'message': '报告生成成功'
                }
            
            elif report_format == 'json':
                report_file = exp_dir / 'results.json'
                with open(report_file, 'w', encoding='utf-8') as f:
                    json.dump(exp['results'], f, indent=2, ensure_ascii=False)
                
                return {
                    'success': True,
                    'report_path': str(report_file),
                    'message': '报告生成成功'
                }
            
            else:
                return {'success': False, 'message': f'不支持的报告格式: {report_format}'}
            
        except Exception as e:
            logger.error(f"生成报告失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'生成失败: {str(e)}'
            }
