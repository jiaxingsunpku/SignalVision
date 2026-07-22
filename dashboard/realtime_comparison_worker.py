"""运行单个隔离的实时对比实验，并把快照写入 JSON 文件。"""

import argparse
import json
import os
import signal
import time
from pathlib import Path

from integration.dashboard_controller import DashboardController
from simulation_config import SimulationConfig


stop_requested = False


def request_stop(_signum, _frame):
    global stop_requested
    stop_requested = True


def write_snapshot(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with open(temporary, 'w', encoding='utf-8') as output:
        json.dump(payload, output, ensure_ascii=False)
    os.replace(temporary, path)


def append_history(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as output:
        output.write(json.dumps(payload, ensure_ascii=False) + '\n')


def build_snapshot(controller, experiment_id, label, running, error=None):
    state = controller.get_current_state() if controller else {}
    junctions = state.get('junctions', [])
    traffic = state.get('traffic_metrics', {})
    congestion = [float(item.get('congestion_level', 0) or 0) for item in junctions]
    return {
        'experiment_id': experiment_id,
        'label': label,
        'running': running,
        'error': error,
        'updated_at': time.time(),
        'step': state.get('current_step', 0),
        'total_steps': state.get('total_steps', 0),
        'simulation_time': state.get('simulation_time', 0),
        'statistics': {
            'total_vehicles': sum(int(item.get('total_vehicles', 0) or 0) for item in junctions),
            'total_waiting': sum(int(item.get('total_halting', 0) or 0) for item in junctions),
            'avg_congestion': sum(congestion) / len(congestion) if congestion else 0,
            'active_vehicles': int(traffic.get('active_vehicles', 0) or 0),
            'departed_total': int(traffic.get('departed_total', 0) or 0),
            'arrived_total': int(traffic.get('arrived_total', 0) or 0),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--experiment-id', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--preset', required=True)
    parser.add_argument('--sim-name', required=True)
    parser.add_argument('--traffic-profile', default='default')
    parser.add_argument('--simlen', type=int, default=3600)
    parser.add_argument('--state-file', required=True)
    parser.add_argument('--history-file', required=True)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    project_root = Path(args.project_root).resolve()
    state_file = Path(args.state_file).resolve()
    history_file = Path(args.history_file).resolve()
    if history_file.exists():
        history_file.unlink()
    config = SimulationConfig(project_root)
    command = config.generate_command(
        args.preset,
        args.sim_name,
        traffic_profile=args.traffic_profile,
        simlen=args.simlen,
    )
    controller = None
    failure = None
    write_snapshot(state_file, {
        'experiment_id': args.experiment_id,
        'label': args.label,
        'running': True,
        'status': 'starting',
        'step': 0,
        'total_steps': args.simlen,
        'statistics': {},
        'updated_at': time.time(),
    })

    try:
        controller = DashboardController(command[2:])
        controller.initialize()
        controller.start()
        for _ in range(args.simlen):
            if stop_requested:
                break
            controller.step()
            snapshot = build_snapshot(controller, args.experiment_id, args.label, True)
            write_snapshot(state_file, snapshot)
            append_history(history_file, snapshot)
    except BaseException as error:
        failure = str(error)
        write_snapshot(
            state_file,
            build_snapshot(
                controller,
                args.experiment_id,
                args.label,
                False,
                str(error),
            ),
        )
        raise
    finally:
        if controller:
            try:
                controller.stop()
            except Exception:
                pass
        final_snapshot = build_snapshot(
            controller,
            args.experiment_id,
            args.label,
            False,
            failure,
        )
        final_snapshot['status'] = 'failed' if failure else ('stopped' if stop_requested else 'completed')
        write_snapshot(state_file, final_snapshot)


if __name__ == '__main__':
    main()
