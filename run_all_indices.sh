#!/usr/bin/env bash
set -euo pipefail

# Runs HD, CD, and TC for NIFTY and SENSEX in parallel,
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

SYMBOLS=(NIFTY SENSEX)
PIDS=()

log_msg() {
  local msg="$1"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "$ts [launcher] $msg" | tee -a "$COMBINED_LOG"
}

display_symbol_output() {
  local symbol="$1"
  local log_file="$2"
  
  if [[ ! -f "$log_file" ]]; then
    return
  fi
  
  # Print box header for symbol
  printf '\n'
  printf '%s\n' "┌─────────────────────────────────────────────────────────────────────────────────┐"
  printf '│ %-77s │\n' "🔹 $symbol"
  printf '%s\n' "├─────────────────────────────────────────────────────────────────────────────────┤"
  
  # Print log content, indented
  while IFS= read -r line; do
    # Truncate long lines to 77 chars to fit in box
    line_truncated="${line:0:77}"
    printf '│ %-77s │\n' "$line_truncated"
  done < "$log_file"
  
  # Print box footer
  printf '%s\n' "└─────────────────────────────────────────────────────────────────────────────────┘"
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
  # Use tr for bash 3.2 compatibility (macOS default)
  symbol_lower=$(echo "$symbol" | tr '[:upper:]' '[:lower:]')
  symbol_log="$RUN_DIR/${symbol_lower}.log"
  log_msg "launching $symbol (log: $symbol_log)"

  (
    PYTHONUNBUFFERED=1 \
      "$PYTHON_BIN" run_strategy.py \
      --script "$symbol" \
      --strategy "$STRATEGIES" \
      --mode "$MODE" \
      --log-level "$LOG_LEVEL" \
      2>&1 >> "$symbol_log"
  ) &

  PIDS+=("$!")
done

log_msg "all runners launched; consolidated log: $COMBINED_LOG"

# Wait for all children to complete and track failures explicitly.
failed_children=0
for pid in "${PIDS[@]}"; do
  if wait "$pid"; then
    :
  else
    child_exit=$?
    failed_children=$((failed_children + 1))
    log_msg "child process pid=$pid exited with code $child_exit"
  fi
done

if (( failed_children > 0 )); then
  exit_code=1
else
  exit_code=0
fi

log_msg "all child processes completed (exit_code=$exit_code)"

# Consolidate all logs into one file for reference
for symbol in "${SYMBOLS[@]}"; do
  symbol_lower=$(echo "$symbol" | tr '[:upper:]' '[:lower:]')
  symbol_log="$RUN_DIR/${symbol_lower}.log"
  if [[ -f "$symbol_log" ]]; then
    {
      echo "═══════════════════════════════════════════════════════════════════════════════"
      echo "                          $symbol OUTPUT"
      echo "═══════════════════════════════════════════════════════════════════════════════"
      cat "$symbol_log"
      echo ""
    } >> "$COMBINED_LOG"
  fi
done

# Display formatted output for each instrument
echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "                    📊 MULTI-STRATEGY EXECUTION RESULTS"
echo "════════════════════════════════════════════════════════════════════════════════"

for symbol in "${SYMBOLS[@]}"; do
  symbol_lower=$(echo "$symbol" | tr '[:upper:]' '[:lower:]')
  symbol_log="$RUN_DIR/${symbol_lower}.log"
  display_symbol_output "$symbol" "$symbol_log"
done

echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "✅ Execution completed | 📁 Logs: $RUN_DIR"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

log_msg "all processes stopped"
exit "$exit_code"
