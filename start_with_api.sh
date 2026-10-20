#!/bin/bash

# Start script that runs both strategy engine and API server

set -e

# Get environment variables
SCRIPT=${SCRIPT:-"NIFTY BANKNIFTY"}
STRATEGY=${STRATEGY:-ema21}
MODE=${MODE:-live}

echo "=========================================="
echo "Starting Trading Strategy Platform"
echo "=========================================="
echo "Script: $SCRIPT"
echo "Strategy: $STRATEGY"
echo "Mode: $MODE"
echo "=========================================="

if [[ "${BACKGROUND_WORKER_ENABLED:-false}" == "true" ]]; then
    echo "[API] Strategy execution is managed from the active dashboard instruments..."
    exec python3 api_server.py
fi

# Start API server in the background
echo "[API] Starting Flask API server on port 5003..."
python3 api_server.py &
API_PID=$!

# Wait for API to start
sleep 3

# Check if API started successfully
if ! kill -0 $API_PID 2>/dev/null; then
    echo "[ERROR] API server failed to start"
    exit 1
fi

echo "[API] API server started (PID: $API_PID)"

# Start strategy engine (foreground)
echo "[STRATEGY] Starting strategy engine..."
exec python3 run_strategy.py --script $SCRIPT --strategy "$STRATEGY" --mode "$MODE"

# If we reach here, the strategy exited
kill $API_PID 2>/dev/null || true
exit 0
