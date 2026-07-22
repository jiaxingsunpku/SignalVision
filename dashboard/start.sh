#!/bin/bash

# SUMO交通监控Dashboard启动脚本

# 默认配置（将从config.json读取，命令行参数优先）
HOST=""
PORT=""
MAP_NAME=""
CONFIG_FILE=""
DEBUG=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --map)
            MAP_NAME="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --debug)
            DEBUG="--debug"
            shift
            ;;
        -h|--help)
            echo "SUMO交通监控Dashboard启动脚本"
            echo ""
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --host HOST         监听地址（默认：从config.json读取）"
            echo "  --port PORT         监听端口（默认：从config.json读取）"
            echo "  --map MAP_NAME      地图名称（默认：从config.json读取）"
            echo "  --config FILE       配置文件路径（默认：dashboard/config.json）"
            echo "  --debug             启用调试模式"
            echo "  -h, --help          显示帮助信息"
            echo ""
            echo "配置文件示例（config.json）："
            echo '  {'
            echo '    "server": {"host": "0.0.0.0", "port": 8080},'
            echo '    "map": {"directory": "cache", "default_map": "81"}'
            echo '  }'
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 切换到dashboard目录
cd "$SCRIPT_DIR"

# 检查并激活conda环境
if command -v conda &> /dev/null; then
    # 检查是否已经在traffic环境中
    if [[ "$CONDA_DEFAULT_ENV" != "traffic" ]]; then
        echo "激活conda环境: traffic"
        # 初始化conda
        eval "$(conda shell.bash hook)"
        conda activate traffic
        if [ $? -ne 0 ]; then
            echo "警告: 无法激活traffic环境，尝试使用当前环境"
        else
            echo "✓ 已激活traffic环境"
        fi
    else
        echo "✓ 已在traffic环境中"
    fi
else
    echo "警告: 未找到conda，使用系统Python"
fi
echo ""

# conda activate 不一定自动设置 SUMO_HOME；优先从当前 Conda 环境发现，
# 否则使用系统安装的 sumo / sumo-gui，避免写死开发机路径。
if [[ -z "$SUMO_HOME" ]]; then
    if [[ -n "$CONDA_PREFIX" && -d "$CONDA_PREFIX/share/sumo" ]]; then
        export SUMO_HOME="$CONDA_PREFIX/share/sumo"
    elif [[ -n "$CONDA_PREFIX" && -d "$CONDA_PREFIX/lib/python3.8/site-packages/sumo" ]]; then
        export SUMO_HOME="$CONDA_PREFIX/lib/python3.8/site-packages/sumo"
    elif command -v sumo &> /dev/null; then
        SUMO_BIN_DIR="$(dirname "$(command -v sumo)")"
        SUMO_PREFIX="$(cd "$SUMO_BIN_DIR/.." && pwd)"
        [[ -d "$SUMO_PREFIX/share/sumo" ]] && export SUMO_HOME="$SUMO_PREFIX/share/sumo"
    fi
fi
if [[ -n "$SUMO_HOME" ]]; then
    export PATH="$SUMO_HOME/bin:$PATH"
    echo "✓ SUMO_HOME=$SUMO_HOME"
else
    echo "警告: 未自动发现 SUMO_HOME；请在启动前手动设置"
fi

# 后台启动 Dashboard 时通常不会继承桌面会话的 X11 授权；sumo-gui 需要
# DISPLAY/XAUTHORITY。GNOME Wayland 下 SUMO-GUI 通过 Xwayland 显示。
if [[ -z "$DISPLAY" && -S "/tmp/.X11-unix/X0" ]]; then
    export DISPLAY=":0"
    echo "✓ DISPLAY=$DISPLAY"
fi
if [[ -z "$XAUTHORITY" ]]; then
    XAUTH_CANDIDATE="$(ls -t "/run/user/$(id -u)"/.mutter-Xwaylandauth.* 2>/dev/null | head -n 1)"
    if [[ -n "$XAUTH_CANDIDATE" ]]; then
        export XAUTHORITY="$XAUTH_CANDIDATE"
        echo "✓ XAUTHORITY=$XAUTHORITY"
    fi
fi

# 检查Python
PYTHON_CMD="python"
if ! command -v python &> /dev/null; then
    PYTHON_CMD="python3"
    if ! command -v python3 &> /dev/null; then
        echo "错误: 未找到 python 或 python3"
        exit 1
    fi
fi

echo "使用Python: $(which $PYTHON_CMD)"
echo "Python版本: $($PYTHON_CMD --version)"
echo ""

# 默认使用 dashboard/config.json
if [[ -z "$CONFIG_FILE" ]]; then
    CONFIG_FILE="$SCRIPT_DIR/config.json"
fi

# 从配置文件补全默认参数
if [[ -f "$CONFIG_FILE" ]]; then
    if [[ -z "$HOST" ]]; then
        HOST="$($PYTHON_CMD - <<PY
import json
with open("$CONFIG_FILE", "r", encoding="utf-8") as f:
    print(json.load(f).get("server", {}).get("host", "0.0.0.0"))
PY
)"
    fi

    if [[ -z "$PORT" ]]; then
        PORT="$($PYTHON_CMD - <<PY
import json
with open("$CONFIG_FILE", "r", encoding="utf-8") as f:
    print(json.load(f).get("server", {}).get("port", 8080))
PY
)"
    fi

    if [[ -z "$MAP_NAME" ]]; then
        MAP_NAME="$($PYTHON_CMD - <<PY
import json
with open("$CONFIG_FILE", "r", encoding="utf-8") as f:
    print(json.load(f).get("map", {}).get("default_map", "81"))
PY
)"
    fi
else
    echo "警告: 配置文件不存在: $CONFIG_FILE"
    [[ -z "$HOST" ]] && HOST="0.0.0.0"
    [[ -z "$PORT" ]] && PORT="8080"
    [[ -z "$MAP_NAME" ]] && MAP_NAME="81"
fi

echo "========================================="
echo "  SUMO交通监控Dashboard"
echo "========================================="
echo "监听地址: $HOST"
echo "监听端口: $PORT"
echo "地图名称: $MAP_NAME"
echo "配置文件: $CONFIG_FILE"
echo "========================================="
echo ""

# 将命令行地图参数同步为运行时环境变量，供 server.py / simulation_config.py 共用
export SUMO_MAP_NAME="$MAP_NAME"

# 检查依赖
echo "检查依赖..."
$PYTHON_CMD -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "错误: Flask未安装"
    echo "请运行: pip install flask flask-cors"
    exit 1
fi

$PYTHON_CMD -c "import flask_cors" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "错误: Flask-CORS未安装"
    echo "请运行: pip install flask flask-cors"
    exit 1
fi

echo "依赖检查完成 ✓"
echo ""

# 构建启动命令
CMD="$PYTHON_CMD server.py"
CMD="$CMD --host $HOST"
CMD="$CMD --port $PORT"
CMD="$CMD --map $MAP_NAME"
CMD="$CMD --config $CONFIG_FILE"
[[ -n "$DEBUG" ]] && CMD="$CMD $DEBUG"

# 启动服务器
echo "启动Dashboard服务器..."
echo "访问地址: http://localhost:$PORT"
echo ""
echo "按 Ctrl+C 停止服务器"
echo ""

eval $CMD
