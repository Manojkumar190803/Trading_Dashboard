#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

PID_FILE="${DASHBOARD_PID_FILE:-$ROOT_DIR/logs/dashboard.pid}"
LOG_FILE="${DASHBOARD_LOG_FILE:-$ROOT_DIR/logs/dashboard.log}"
HOST="${STREAMLIT_SERVER_ADDRESS:-localhost}"
PORT="${STREAMLIT_SERVER_PORT:-8501}"

mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")"

read_pid() {
  [[ -f "$PID_FILE" ]] && cat "$PID_FILE"
}

is_running() {
  local pid
  pid="$(read_pid)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_dashboard() {
  if is_running; then
    echo "Dashboard is already running (pid $(read_pid))."
    echo "URL: http://$HOST:$PORT"
    return 0
  fi

  rm -f "$PID_FILE"
  nohup "$PYTHON_BIN" -m streamlit run frontend/strategy_dashboard.py \
    --server.address="$HOST" \
    --server.port="$PORT" \
    --server.headless=true \
    > "$LOG_FILE" 2>&1 < /dev/null &
  echo $! > "$PID_FILE"

  echo "Dashboard started in background (pid $(read_pid))."
  echo "URL: http://$HOST:$PORT"
  echo "Log: $LOG_FILE"
}

stop_dashboard() {
  if ! is_running; then
    rm -f "$PID_FILE"
    echo "Dashboard is not running."
    return 0
  fi

  local pid
  pid="$(read_pid)"
  kill "$pid"
  rm -f "$PID_FILE"
  echo "Dashboard stopped (pid $pid)."
}

status_dashboard() {
  if is_running; then
    echo "Dashboard is running (pid $(read_pid))."
    echo "URL: http://$HOST:$PORT"
  else
    rm -f "$PID_FILE"
    echo "Dashboard is not running."
    return 1
  fi
}

case "${1:-start}" in
  start)
    start_dashboard
    ;;
  stop)
    stop_dashboard
    ;;
  restart)
    stop_dashboard
    start_dashboard
    ;;
  status)
    status_dashboard
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 2
    ;;
esac