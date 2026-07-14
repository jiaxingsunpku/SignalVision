# Repository Guidelines

## Project Structure & Module Organization

SignalVision combines a traffic-signal simulation runtime with a browser dashboard. Core training and simulation code lives in `runtime/`: agents are in `runtime/agent/`, simulator backends in `runtime/world/`, runners in `runtime/runner/`, tasks in `runtime/task/`, generated data utilities in `runtime/tools/`, and sample networks under `runtime/data/raw_data/`. The dashboard is in `dashboard/`, with `server.py` as the Flask entry point, `templates/` for HTML, `static/css/` and `static/js/` for frontend assets, and `integration/` plus `dashboard_tools/` for runtime-facing services. The `adapter/` package bridges the dashboard to the runtime through `standard_interface.py`, `libsignal_adapter.py`, and config/network loaders.

## Build, Test, and Development Commands

Create an isolated Python environment first. Install base runtime dependencies with:

```bash
pip install -r runtime/requirements.txt
pip install flask flask-cors
```

SUMO is required for the default simulator; set `SUMO_HOME` before running runtime or dashboard flows. Common commands:

```bash
cd runtime && python run.py -a maxpressure -n ezhou -w sumo
cd dashboard && ./start.sh --port 8080 --map 81
python -m compileall adapter runtime dashboard
```

The first command runs a simulation experiment, the second starts the web dashboard, and the third catches Python syntax/import issues without executing full simulations.

## Coding Style & Naming Conventions

Use Python 3 with 4-space indentation. Follow existing module style: `snake_case` for files, functions, and variables; `PascalCase` for classes; uppercase names only for constants. Keep runtime additions registered through the existing registry/interface pattern instead of hard-coding cross-module imports. Frontend files are plain HTML/CSS/JavaScript; keep assets in the existing `dashboard/static/` subdirectories.

## Testing Guidelines

No formal test suite is currently present. For small changes, run `python -m compileall adapter runtime dashboard` and a focused smoke command for the touched area. When adding tests, prefer `pytest`, place them under `tests/` or beside the module as `test_<module>.py`, and avoid relying on large generated outputs.

## Commit & Pull Request Guidelines

Recent commits use conventional prefixes with Chinese summaries, for example `chore: 保留 ezhou 示例模型`. Keep messages concise and scoped, such as `fix: 修复 dashboard 地图加载`. Pull requests should describe the affected runtime/dashboard area, list verification commands, mention SUMO or dataset requirements, and include screenshots for visible dashboard changes.

## Security & Configuration Tips

Do not commit secrets, local environments, caches, logs, generated model outputs, or process files. Keep environment-specific values in local config files and verify `.gitignore` before staging generated artifacts.
