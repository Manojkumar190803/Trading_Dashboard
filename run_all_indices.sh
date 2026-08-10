#!/usr/bin/env bash
set -euo pipefail

# Runs HD, CD, and TC for NIFTY/BANKNIFTY/SENSEX in parallel,
# and writes both per-symbol logs plus one consolidated tagged log.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

MODE="${MODE:-live}"
STRATEGIES="${STRATEGIES:-hd,cd,tc}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
LOG_BASE_DIR="${LOG_BASE_DIR:-$ROOT_DIR/logs/live_runs}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$LOG_BASE_DIR/$RUN_ID"

mkdir -p "$RUN_DIR"
COMBINED_LOG="$RUN_DIR/consolidated.log"

SYMBOLS=(NIFTY BANKNIFTY SENSEX)
PIDS=()

log_msg() {
  local msg="$1"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "$ts [launcher] $msg" | tee -a "$COMBINED_LOG"
}

cleanup() {
  log_msg "shutdown requested, stopping child processes..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  # Give processes a brief chance to exit gracefully.
  sleep 1

  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup INT TERM

log_msg "starting parallel runners"
log_msg "python=$PYTHON_BIN mode=$MODE strategies=$STRATEGIES"
log_msg "run_dir=$RUN_DIR"

for symbol in "${SYMBOLS[@]}"; do
  symbol_log="$RUN_DIR/${symbol,,}.log"
  log_msg "launching $symbol (log: $symbol_log)"

  (
    PYTHONUNBUFFERED=1 \
      "$PYTHON_BIN" run_strategy.py \
      --script "$symbol" \
      --strategy "$STRATEGIES" \
      --mode "$MODE" \
      --log-level "$LOG_LEVEL" \
      2>&1 \
    | while IFS= read -r line; do
        printf "%s [%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$symbol" "$line"
      done \
    | tee -a "$symbol_log" \
    | tee -a "$COMBINED_LOG"
  ) &

  PIDS+=("$!")
done

log_msg "all runners launched; consolidated log: $COMBINED_LOG"

# Wait for any child to exit. If one exits unexpectedly, stop all for consistency.
set +e
wait -n "${PIDS[@]}"
exit_code=$?
set -e

log_msg "a child process exited (code=$exit_code); stopping remaining processes"
cleanup

# Reap remaining children to avoid zombies.
for pid in "${PIDS[@]:-}"; do
  wait "$pid" 2>/dev/null || true
done

log_msg "all processes stopped"
exit "$exit_code"
