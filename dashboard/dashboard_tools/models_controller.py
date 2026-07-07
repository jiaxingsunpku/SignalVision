"""
模型管理控制器
负责管理PPO模型的存储、加载和版本控制
"""

import os
import sys
import logging
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


class ModelsController:
    """
    模型管理控制器
    管理模型相关功能，包括：
    - 模型列表查看
    - 模型加载和切换
    - 模型版本管理
    - 模型性能评估
    """
    
    def __init__(self):
        """初始化模型管理控制器"""
        # LibSignal 运行时的模型输出目录
        self.log_dir = PROJECT_ROOT / "runtime" / "data" / "output_data" / "tsc"
        self.current_model = None
        logger.info(f"模型管理控制器初始化完成，模型目录: {self.log_dir}")

    @staticmethod
    def _normalize_algorithm_name(agent_dir_name):
        if agent_dir_name == 'sumo_ppo_pfrl':
            return 'ppo'
        if agent_dir_name.startswith('sumo_') and agent_dir_name.endswith('_agent'):
            return agent_dir_name.replace('sumo_', '').replace('_pytorch_agent', '').replace('_agent', '')
        return agent_dir_name.replace('sumo_', '')
    
    def list_models(self, filters=None):
        """
        列出所有可用模型
        
        Args:
            filters (dict): 过滤条件
                - algorithm: 算法类型 (ppo, maxpressure)
                - model_name: 模型名称
        
        Returns:
            dict: 模型列表
        """
        try:
            logger.info(f"查询模型列表: {filters}")
            
            models = []
            
            if not self.log_dir.exists():
                logger.warning(f"日志目录不存在: {self.log_dir}")
                return {
                    'success': True,
                    'models': [],
                    'total': 0
                }
            
            # 扫描 LibSignal 运行时目录结构
            # runtime/data/output_data/tsc/
            #   └── sumo_{agent_name}/  (如 sumo_colight_pytorch_agent)
            #       └── sumo{network}/  (如 sumo81)
            #           └── {prefix}/  (模型名称)
            #               └── model/  (模型文件)
            for agent_dir in self.log_dir.iterdir():
                if not agent_dir.is_dir():
                    continue
                
                agent_name = agent_dir.name
                algorithm = self._normalize_algorithm_name(agent_name)
                
                # 应用算法过滤条件
                if filters and filters.get('algorithm') and filters['algorithm'] != algorithm:
                    continue
                
                # 扫描网络目录
                for network_dir in agent_dir.iterdir():
                    if not network_dir.is_dir():
                        continue
                    
                    # 扫描模型前缀（训练名称）目录
                    for model_prefix_dir in network_dir.iterdir():
                        if not model_prefix_dir.is_dir():
                            continue
                        
                        model_name = model_prefix_dir.name
                        
                        # 应用模型名称过滤
                        if filters and filters.get('model_name') and filters['model_name'] not in model_name:
                            continue
                        
                        # 读取模型信息
                        model_info = self._get_libsignal_model_info(algorithm, agent_name, network_dir.name, model_name, model_prefix_dir)
                        if model_info:
                            models.append(model_info)
            
            # 按修改时间排序（最新的在前）
            models.sort(key=lambda x: x.get('modified_time', 0), reverse=True)
            
            return {
                'success': True,
                'models': models,
                'total': len(models)
            }
            
        except Exception as e:
            logger.error(f"查询模型列表失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'查询失败: {str(e)}'
            }
    
    def _get_libsignal_model_info(self, algorithm, agent_name, network_name, model_name, model_dir):
        """从 LibSignal 模型目录提取信息"""
        try:
            info = {
                'id': f"{algorithm}/{network_name}/{model_name}",
                'algorithm': algorithm,
                'agent': agent_name,
                'network': network_name,
                'name': model_name,
                'sim': network_name,  # 添加 sim 字段用于前端显示
                'path': str(model_dir),
                'has_weights': False,
                'has_params': False,
                'has_metrics': False,
                'weight_count': 0,
                'max_epoch': None,  # 添加 max_epoch 用于前端显示
                'modified_time': model_dir.stat().st_mtime
            }
            
            # LibSignal 的模型文件在 model/ 目录下
            model_files_dir = model_dir / 'model'
            if model_files_dir.exists() and model_files_dir.is_dir():
                info['has_weights'] = True
                weight_files = list(model_files_dir.glob('*.pt'))
                info['weight_count'] = len(weight_files)
                
                # 提取 epoch 信息（LibSignal 格式：{epoch}_{step}.pt）
                if weight_files:
                    epochs = []
                    for wf in weight_files:
                        try:
                            # 文件名格式：130_0.pt -> epoch 130
                            epoch_str = wf.stem.split('_')[0]
                            epoch = int(epoch_str)
                            epochs.append(epoch)
                        except:
                            pass
                    
                    if epochs:
                        info['epochs'] = sorted(list(set(epochs)))  # 去重并排序
                        info['latest_epoch'] = max(epochs)
                        info['earliest_epoch'] = min(epochs)
                        info['max_epoch'] = max(epochs)  # 添加用于前端显示
            
            # 检查 logger 目录（日志和指标）
            logger_dir = model_dir / 'logger'
            if logger_dir.exists() and logger_dir.is_dir():
                info['has_metrics'] = True
                # 可以进一步解析日志文件获取指标
            
            # 检查配置文件
            config_file = model_dir / 'dashboard_config.json'
            if config_file.exists():
                import json
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    info['config'] = config
                    info['has_params'] = True
            
            return info
            
        except Exception as e:
            logger.warning(f"解析模型信息失败 {model_dir}: {e}")
            return None
    
    def _get_model_info_from_dir(self, algorithm, model_name, model_dir):
        """从模型目录提取信息"""
        try:
            info = {
                'id': f"{algorithm}/{model_name}",
                'algorithm': algorithm,
                'name': model_name,
                'path': str(model_dir),
                'has_weights': False,
                'has_params': False,
                'has_metrics': False,
                'weight_count': 0,
                'modified_time': model_dir.stat().st_mtime
            }
            
            # 检查weights目录
            weights_dir = model_dir / 'weights'
            if weights_dir.exists() and weights_dir.is_dir():
                info['has_weights'] = True
                weight_files = list(weights_dir.glob('*.pt'))
                info['weight_count'] = len(weight_files)
                
                # 提取epoch信息
                if weight_files:
                    epochs = []
                    for wf in weight_files:
                        # 从文件名提取epoch，如 model_J0_epoch50.pt
                        parts = wf.stem.split('_')
                        for i, part in enumerate(parts):
                            if part.startswith('epoch'):
                                try:
                                    epoch = int(part.replace('epoch', ''))
                                    epochs.append(epoch)
                                except:
                                    pass
                    if epochs:
                        info['max_epoch'] = max(epochs)
            
            # 检查training_params.json
            params_file = model_dir / 'training_params.json'
            if params_file.exists():
                info['has_params'] = True
                info['params_file'] = str(params_file)
                
                # 读取部分参数信息
                try:
                    import json
                    with open(params_file, 'r') as f:
                        params = json.load(f)
                        info['sim'] = params.get('sim', 'unknown')
                        info['n_epochs'] = params.get('n_epochs', 0)
                        info['description'] = params.get('description', '')
                except Exception as e:
                    logger.warning(f"读取参数文件失败: {e}")
            
            # 检查training_metrics.png
            metrics_file = model_dir / 'training_metrics.png'
            if metrics_file.exists():
                info['has_metrics'] = True
                info['metrics_file'] = str(metrics_file)
            
            return info
            
        except Exception as e:
            logger.error(f"提取模型信息失败 {model_dir}: {e}")
            return None
    
    def load_model(self, model_id):
        """
        加载指定模型
        
        Args:
            model_id (str): 模型ID
        
        Returns:
            dict: 加载结果
        """
        try:
            logger.info(f"加载模型: {model_id}")
            
            # TODO: 实现模型加载逻辑
            # 1. 验证模型ID
            # 2. 加载模型文件
            # 3. 更新当前模型状态
            
            self.current_model = model_id
            
            return {
                'success': True,
                'message': '模型加载成功'
            }
            
        except Exception as e:
            logger.error(f"模型加载失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'加载失败: {str(e)}'
            }
    
    def delete_model(self, model_id):
        """
        删除指定模型
        
        Args:
            model_id (str): 模型ID
        
        Returns:
            dict: 删除结果
        """
        try:
            logger.info(f"删除模型: {model_id}")
            
            # TODO: 实现模型删除逻辑
            # 1. 验证模型ID
            # 2. 检查是否为当前模型
            # 3. 删除模型文件
            
            return {
                'success': True,
                'message': '模型删除成功'
            }
            
        except Exception as e:
            logger.error(f"模型删除失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'删除失败: {str(e)}'
            }
    
    def get_model_info(self, model_id):
        """
        获取模型详细信息
        
        Args:
            model_id (str): 模型ID，格式为 "algorithm/network/model_name"
        
        Returns:
            dict: 模型信息
        """
        try:
            logger.info(f"获取模型信息: {model_id}")
            
            # 解析model_id (LibSignal格式: algorithm/network/model_name)
            parts = model_id.split('/')
            if len(parts) != 3:
                return {
                    'success': False,
                    'message': f'Invalid model_id format (expected algorithm/network/model_name): {model_id}'
                }
            
            algorithm, network_name, model_name = parts
            
            # 找到对应的agent目录
            agent_dir = None
            for d in self.log_dir.iterdir():
                if not d.is_dir():
                    continue
                if self._normalize_algorithm_name(d.name) == algorithm:
                    agent_dir = d
                    break
            
            if not agent_dir:
                return {
                    'success': False,
                    'message': f'Agent directory not found for algorithm: {algorithm}'
                }
            
            # 构建完整路径
            model_dir = agent_dir / network_name / model_name
            
            if not model_dir.exists():
                return {
                    'success': False,
                    'message': f'Model directory not found: {model_dir}'
                }
            
            # 获取基本信息（使用LibSignal的方法）
            agent_name = agent_dir.name
            model_info = self._get_libsignal_model_info(algorithm, agent_name, network_name, model_name, model_dir)
            
            if not model_info:
                return {
                    'success': False,
                    'message': 'Failed to parse model information'
                }
            
            # 读取完整的训练参数（LibSignal使用dashboard_config.json）
            config_file = model_dir / 'dashboard_config.json'
            if config_file.exists():
                try:
                    import json
                    with open(config_file, 'r') as f:
                        model_info['parameters'] = json.load(f)
                except Exception as e:
                    logger.warning(f"读取配置文件失败: {e}")
                    model_info['parameters'] = {}
            else:
                    model_info['parameters'] = {}
            
            return {
                'success': True,
                'model_info': model_info
            }
            
        except Exception as e:
            logger.error(f"获取模型信息失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }
    
    def evaluate_model(self, model_id, eval_params):
        """
        评估模型性能
        
        Args:
            model_id (str): 模型ID
            eval_params (dict): 评估参数
        
        Returns:
            dict: 评估结果
        """
        try:
            logger.info(f"评估模型: {model_id}, 参数: {eval_params}")
            
            # TODO: 实现模型评估逻辑
            
            return {
                'success': True,
                'evaluation': {}
            }
            
        except Exception as e:
            logger.error(f"模型评估失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'评估失败: {str(e)}'
            }
    
    def get_model_file(self, model_id, file_type):
        """
        获取模型文件路径
        
        Args:
            model_id (str): 模型ID (LibSignal格式: algorithm/network/model_name)
            file_type (str): 文件类型 (params, metrics)
        
        Returns:
            dict: 文件路径信息
        """
        try:
            # 解析model_id
            parts = model_id.split('/')
            if len(parts) != 3:
                return {
                    'success': False,
                    'message': f'Invalid model_id format: {model_id}'
                }
            
            algorithm, network_name, model_name = parts
            
            # 找到对应的agent目录
            agent_dir = None
            for d in self.log_dir.iterdir():
                if not d.is_dir():
                    continue
                if self._normalize_algorithm_name(d.name) == algorithm:
                    agent_dir = d
                    break
            
            if not agent_dir:
                return {
                    'success': False,
                    'message': f'Agent directory not found for algorithm: {algorithm}'
                }
            
            model_dir = agent_dir / network_name / model_name
            
            if not model_dir.exists():
                return {
                    'success': False,
                    'message': 'Model not found'
                }
            
            if file_type == 'params':
                # LibSignal使用dashboard_config.json
                file_path = model_dir / 'dashboard_config.json'
            elif file_type == 'metrics':
                # LibSignal没有预生成的metrics图，尝试从logger目录生成
                file_path = self._generate_metrics_image(model_dir)
                if not file_path:
                    return {
                        'success': False,
                        'message': 'Metrics image not available'
                    }
            else:
                return {
                    'success': False,
                    'message': f'Unknown file type: {file_type}'
                }
            
            if not file_path.exists():
                return {
                    'success': False,
                    'message': f'File not found: {file_path.name}'
                }
            
            return {
                'success': True,
                'file_path': str(file_path),
                'file_name': file_path.name
            }
            
        except Exception as e:
            logger.error(f"获取模型文件失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }
    
    def _generate_metrics_image(self, model_dir):
        """
        从LibSignal的日志文件生成训练指标图
        
        Args:
            model_dir (Path): 模型目录
        
        Returns:
            Path: 生成的图片路径，如果失败返回None
        """
        try:
            import matplotlib
            matplotlib.use('Agg')  # 使用非交互式后端
            import matplotlib.pyplot as plt
            import re
            from datetime import datetime
            
            logger_dir = model_dir / 'logger'
            if not logger_dir.exists():
                logger.warning(f"Logger目录不存在: {logger_dir}")
                return None
            
            # 查找日志文件（LibSignal格式：train_xxx_DTL.log）
            log_files = list(logger_dir.glob('*_DTL.log'))
            if not log_files:
                logger.warning(f"未找到训练日志文件: {logger_dir}")
                return None
            
            log_file = log_files[0]  # 使用第一个日志文件
            
            # 解析日志文件
            epochs = []
            travel_times = []
            losses = []
            rewards = []
            
            with open(log_file, 'r') as f:
                for line in f:
                    # 解析LibSignal日志格式：TRAIN: Epoch X, Travel Time: Y, Loss: Z, Reward: W
                    if line.startswith('TRAIN'):
                        try:
                            parts = line.strip().split(',')
                            epoch = int(parts[0].split(':')[1].strip().split()[1])
                            travel_time = float(parts[1].split(':')[1].strip())
                            loss = float(parts[2].split(':')[1].strip())
                            reward = float(parts[3].split(':')[1].strip())
                            
                            epochs.append(epoch)
                            travel_times.append(travel_time)
                            losses.append(loss)
                            rewards.append(reward)
                        except Exception as e:
                            logger.debug(f"跳过解析日志行: {line.strip()}, 错误: {e}")
                            continue
            
            if not epochs:
                logger.warning(f"日志文件中未找到有效的训练数据: {log_file}")
                return None
            
            # 生成图表
            fig, axes = plt.subplots(2, 2, figsize=(12, 8))
            fig.suptitle('Training Metrics', fontsize=16)
            
            # Travel Time
            axes[0, 0].plot(epochs, travel_times, 'b-', linewidth=2)
            axes[0, 0].set_xlabel('Epoch')
            axes[0, 0].set_ylabel('Travel Time')
            axes[0, 0].set_title('Average Travel Time')
            axes[0, 0].grid(True, alpha=0.3)
            
            # Loss
            axes[0, 1].plot(epochs, losses, 'r-', linewidth=2)
            axes[0, 1].set_xlabel('Epoch')
            axes[0, 1].set_ylabel('Loss')
            axes[0, 1].set_title('Training Loss')
            axes[0, 1].grid(True, alpha=0.3)
            
            # Reward
            axes[1, 0].plot(epochs, rewards, 'g-', linewidth=2)
            axes[1, 0].set_xlabel('Epoch')
            axes[1, 0].set_ylabel('Reward')
            axes[1, 0].set_title('Average Reward')
            axes[1, 0].grid(True, alpha=0.3)
            
            # 移除第四个子图
            fig.delaxes(axes[1, 1])
            
            plt.tight_layout()
            
            # 保存图片
            output_path = model_dir / 'training_metrics.png'
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            logger.info(f"生成训练指标图: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"生成训练指标图失败: {e}", exc_info=True)
            return None
