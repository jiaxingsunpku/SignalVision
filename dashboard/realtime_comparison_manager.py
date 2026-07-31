"""管理 FixedTime 与 PPO 实时对比，并持久化每次试验的完整过程。"""

from datetime import datetime, timezone
import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path


class RealtimeComparisonManager:
    EXPERIMENTS = (
        {'id': 'fixedtime', 'label': 'FixedTime 固定配时', 'preset': 'fixedtime'},
        {'id': 'ppo', 'label': 'PPO-PFRL', 'preset': 'ppo'},
    )

    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.runtime_dir = self.project_root / 'dashboard' / 'cache' / 'realtime_comparison'
        self.history_dir = self.project_root / 'dashboard' / 'data' / 'comparison_history'
        self.history_trash_dir = self.history_dir / '.trash'
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.processes = {}
        self.log_handles = {}
        self.config = None
        self.paused = False
        self.deleted_sessions = set()
        self._lock = threading.RLock()

    @staticmethod
    def _now_iso():
        return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')

    @property
    def running(self):
        return any(process.poll() is None for process in self.processes.values())

    def _session_dir(self):
        session_id = (self.config or {}).get('session_id', 'unassigned')
        return self.runtime_dir / session_id

    def _state_file(self, experiment_id):
        return self._session_dir() / f'{experiment_id}.json'

    def _series_file(self, experiment_id):
        return self._session_dir() / f'{experiment_id}.ndjson'

    def start(self, sim_name, traffic_profile='default', simlen=3600, gui=True,
              traffic_metadata=None):
        with self._lock:
            if self.running:
                return {'success': False, 'message': '对比实验已在运行中'}

            self.stop()
            session_id = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
            self.config = {
                'session_id': session_id,
                'created_at': self._now_iso(),
                'sim_name': sim_name,
                'traffic_profile': traffic_profile,
                'traffic': traffic_metadata or {'id': traffic_profile},
                'simlen': int(simlen),
                'gui': bool(gui),
                'algorithms': [
                    {'id': item['id'], 'label': item['label'], 'preset': item['preset']}
                    for item in self.EXPERIMENTS
                ],
            }
            self._session_dir().mkdir(parents=True, exist_ok=True)
            self.paused = False
            worker = self.project_root / 'dashboard' / 'realtime_comparison_worker.py'
            for experiment in self.EXPERIMENTS:
                state_file = self._state_file(experiment['id'])
                series_file = self._series_file(experiment['id'])
                log_file = self._session_dir() / f"{experiment['id']}.log"
                log_handle = open(log_file, 'w', encoding='utf-8')
                command = [
                    sys.executable,
                    '-u',
                    str(worker),
                    '--project-root', str(self.project_root),
                    '--experiment-id', experiment['id'],
                    '--label', experiment['label'],
                    '--preset', f"{experiment['preset']}_gui" if gui else experiment['preset'],
                    '--sim-name', sim_name,
                    '--traffic-profile', traffic_profile,
                    '--simlen', str(int(simlen)),
                    '--state-file', str(state_file),
                    '--history-file', str(series_file),
                ]
                self.log_handles[experiment['id']] = log_handle
                self.processes[experiment['id']] = subprocess.Popen(
                    command,
                    cwd=str(self.project_root / 'dashboard'),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

            process_snapshot = list(self.processes.values())
            threading.Thread(
                target=self._watch_completion,
                args=(session_id, process_snapshot),
                daemon=True,
            ).start()
            return {
                'success': True,
                'message': 'FixedTime 与 PPO 对比实验已启动，并将自动保存结果',
                'config': self.config,
            }

    def _watch_completion(self, session_id, processes):
        for process in processes:
            try:
                process.wait()
            except Exception:
                return
        with self._lock:
            if (self.config or {}).get('session_id') != session_id:
                return
            self._close_logs()
            self._archive_current()

    def _close_logs(self):
        for handle in self.log_handles.values():
            try:
                handle.close()
            except Exception:
                pass
        self.log_handles = {}

    def stop(self):
        with self._lock:
            processes = list(self.processes.values())
            if self.paused:
                for process in processes:
                    if process.poll() is None:
                        os.kill(process.pid, signal.SIGCONT)
                self.paused = False
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                if process.poll() is None:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            self._close_logs()
            self._archive_current()
            self.processes = {}
            return {'success': True, 'message': '对比实验已停止，结果已保存'}

    def pause(self):
        with self._lock:
            live_processes = [process for process in self.processes.values() if process.poll() is None]
            if not live_processes:
                return {'success': False, 'message': '没有正在运行的对比实验'}
            if not self.paused:
                for process in live_processes:
                    os.kill(process.pid, signal.SIGSTOP)
                self.paused = True
            return {'success': True, 'message': '两个对比实验已暂停', 'paused': True}

    def resume(self):
        with self._lock:
            live_processes = [process for process in self.processes.values() if process.poll() is None]
            if not live_processes:
                return {'success': False, 'message': '没有可继续的对比实验'}
            if self.paused:
                for process in live_processes:
                    os.kill(process.pid, signal.SIGCONT)
                self.paused = False
            return {'success': True, 'message': '两个对比实验已继续', 'paused': False}

    def _read_state(self, experiment):
        state_file = self._state_file(experiment['id'])
        state = {
            'experiment_id': experiment['id'],
            'label': experiment['label'],
            'running': False,
            'status': 'waiting',
            'statistics': {},
        }
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as source:
                    state.update(json.load(source))
            except (OSError, ValueError):
                state['status'] = 'starting'

        process = self.processes.get(experiment['id'])
        if process:
            state['running'] = process.poll() is None
            state['exit_code'] = process.poll()
            if state['running'] and state.get('status') in ('waiting', 'stopped', 'completed'):
                state['status'] = 'running'
            if state['running'] and self.paused:
                state['status'] = 'paused'
        return state

    @staticmethod
    def _read_series(path):
        samples = []
        if not path.exists():
            return samples
        try:
            with open(path, 'r', encoding='utf-8') as source:
                for line in source:
                    try:
                        sample = json.loads(line)
                    except ValueError:
                        continue
                    if sample.get('step', 0) > 0:
                        samples.append(sample)
        except OSError:
            return []
        return samples

    @staticmethod
    def _downsample_series(samples, max_points):
        """等距保留完整时间范围，始终包含首尾采样点。"""
        if len(samples) <= max_points:
            return samples
        if max_points <= 1:
            return [samples[-1]]
        last_index = len(samples) - 1
        indices = {
            round(index * last_index / (max_points - 1))
            for index in range(max_points)
        }
        return [samples[index] for index in sorted(indices)]

    def get_live_history(self, max_points=600):
        """读取当前试验从启动至今的后端序列，供页面中途打开时回填。"""
        with self._lock:
            if not self.config:
                return {
                    'success': True,
                    'session_id': None,
                    'config': None,
                    'experiments': [],
                }
            max_points = max(2, min(int(max_points), 3600))
            experiments = []
            for definition in self.EXPERIMENTS:
                samples = self._read_series(self._series_file(definition['id']))
                experiments.append({
                    'experiment_id': definition['id'],
                    'label': definition['label'],
                    'series': self._downsample_series(samples, max_points),
                    'sample_count': len(samples),
                })
            return {
                'success': True,
                'session_id': self.config.get('session_id'),
                'config': self.config,
                'experiments': experiments,
            }

    @staticmethod
    def _summarize_series(samples, final_state):
        stats = [item.get('statistics', {}) for item in samples]
        waiting = [float(item.get('total_waiting', 0) or 0) for item in stats]
        congestion = [float(item.get('avg_congestion', 0) or 0) for item in stats]
        active = [float(item.get('active_vehicles', 0) or 0) for item in stats]
        arrived = [int(item.get('arrived_total', 0) or 0) for item in stats]
        final_stats = final_state.get('statistics', {})
        return {
            'status': final_state.get('status', 'unknown'),
            'steps': int(final_state.get('step', 0) or 0),
            'samples': len(samples),
            'mean_waiting': sum(waiting) / len(waiting) if waiting else 0,
            'peak_waiting': max(waiting, default=0),
            'mean_congestion': sum(congestion) / len(congestion) if congestion else 0,
            'peak_active': max(active, default=0),
            'arrived_total': max(arrived, default=int(final_stats.get('arrived_total', 0) or 0)),
            'departed_total': int(final_stats.get('departed_total', 0) or 0),
        }

    def _archive_current(self):
        if not self.config:
            return None
        if self.config.get('session_id') in self.deleted_sessions:
            return None
        experiments = []
        for definition in self.EXPERIMENTS:
            final_state = self._read_state(definition)
            series = self._read_series(self._series_file(definition['id']))
            experiments.append({
                'experiment_id': definition['id'],
                'label': definition['label'],
                'final_state': final_state,
                'summary': self._summarize_series(series, final_state),
                'series': series,
            })
        payload = {
            'session_id': self.config['session_id'],
            'created_at': self.config['created_at'],
            'saved_at': self._now_iso(),
            'config': self.config,
            'experiments': experiments,
        }
        target = self.history_dir / f"{self.config['session_id']}.json"
        temporary = target.with_suffix('.json.tmp')
        with open(temporary, 'w', encoding='utf-8') as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
        return payload

    def list_history(self, limit=50):
        records = []
        for path in sorted(self.history_dir.glob('*.json'), reverse=True)[:max(1, min(limit, 1000))]:
            try:
                with open(path, 'r', encoding='utf-8') as source:
                    payload = json.load(source)
            except (OSError, ValueError):
                continue
            records.append({
                'session_id': payload.get('session_id'),
                'created_at': payload.get('created_at'),
                'saved_at': payload.get('saved_at'),
                'config': payload.get('config', {}),
                'experiments': [
                    {
                        'experiment_id': item.get('experiment_id'),
                        'label': item.get('label'),
                        'summary': item.get('summary', {}),
                    }
                    for item in payload.get('experiments', [])
                ],
            })
        return {'success': True, 'records': records}

    def get_history(self, session_id):
        if not session_id or Path(session_id).name != session_id:
            return {'success': False, 'message': '无效的试验编号'}
        path = self.history_dir / f'{session_id}.json'
        if not path.exists():
            return {'success': False, 'message': '未找到该历史试验'}
        try:
            with open(path, 'r', encoding='utf-8') as source:
                return {'success': True, 'record': json.load(source)}
        except (OSError, ValueError) as error:
            return {'success': False, 'message': str(error)}

    def _move_to_history_trash(self, path):
        """将历史记录移入本地回收目录，避免界面删除后不可恢复。"""
        self.history_trash_dir.mkdir(parents=True, exist_ok=True)
        target = self.history_trash_dir / path.name
        if target.exists():
            target = self.history_trash_dir / f'{path.stem}-{datetime.now().strftime("%Y%m%d%H%M%S")}.json'
        os.replace(path, target)
        return target

    def delete_history(self, session_id):
        with self._lock:
            if not session_id or Path(session_id).name != session_id:
                return {'success': False, 'message': '无效的试验编号'}
            path = self.history_dir / f'{session_id}.json'
            if not path.exists():
                return {'success': False, 'message': '未找到该历史试验'}
            self._move_to_history_trash(path)
            self.deleted_sessions.add(session_id)
            return {'success': True, 'message': '历史试验已删除', 'deleted': [session_id]}

    def delete_history_bulk(self, mode, value):
        """按创建日期或实际运行步数批量移入回收目录。"""
        if mode not in {'before_date', 'shorter_than'}:
            return {'success': False, 'message': '不支持的批量删除条件'}
        deleted = []
        with self._lock:
            for path in sorted(self.history_dir.glob('*.json')):
                try:
                    with open(path, 'r', encoding='utf-8') as source:
                        payload = json.load(source)
                except (OSError, ValueError):
                    continue

                if mode == 'before_date':
                    created_date = str(payload.get('created_at') or '')[:10]
                    matched = bool(created_date and created_date < str(value))
                else:
                    summaries = [item.get('summary', {}) for item in payload.get('experiments', [])]
                    actual_steps = max((int(item.get('steps', 0) or 0) for item in summaries), default=0)
                    matched = actual_steps < int(value)
                if not matched:
                    continue

                self._move_to_history_trash(path)
                session_id = payload.get('session_id') or path.stem
                self.deleted_sessions.add(session_id)
                deleted.append(session_id)
        return {
            'success': True,
            'message': f'已删除 {len(deleted)} 条历史试验',
            'deleted': deleted,
        }

    def get_status(self):
        experiments = [self._read_state(item) for item in self.EXPERIMENTS]
        return {
            'success': True,
            'running': any(item.get('running') for item in experiments),
            'paused': self.paused,
            'config': self.config,
            'experiments': experiments,
        }
