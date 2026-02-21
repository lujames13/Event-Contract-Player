#!/bin/bash
# scripts/run_live_supervised.sh — Supervised live runner with auto-restart

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/live.pid"

RESTART_DELAY=5
MAX_RESTART_DELAY=300
MAX_RESTARTS_PER_HOUR=10

mkdir -p "$LOG_DIR"

cleanup() {
    echo ""
    echo "[supervisor] Termination signal received. Cleaning up..."
    # Kill child process gracefully
    if [ -n "${CHILD_PID:-}" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
        echo "[supervisor] Stopping run_live.py (PID: $CHILD_PID)..."
        kill -INT "$CHILD_PID"
        # Wait up to 10 seconds for graceful shutdown
        for i in $(seq 1 10); do
            kill -0 "$CHILD_PID" 2>/dev/null || break
            sleep 1
        done
        # Force kill if still alive
        if kill -0 "$CHILD_PID" 2>/dev/null; then
            echo "[supervisor] run_live.py still alive, force killing..."
            kill -9 "$CHILD_PID"
        fi
    fi
    rm -f "$PID_FILE"
    echo "[supervisor] Stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

restart_count=0
restart_window_start=$(date +%s)

while true; do
    LOG_FILE="$LOG_DIR/live_$(date +%Y%m%d).log"
    
    echo "[supervisor] Starting run_live.py at $(date)" | tee -a "$LOG_FILE"
    
    cd "$PROJECT_DIR"
    # Pass all arguments to run_live.py
    PYTHONPATH=src uv run python scripts/run_live.py "$@" >> "$LOG_FILE" 2>&1 &
    CHILD_PID=$!
    echo "$CHILD_PID" > "$PID_FILE"
    
    wait "$CHILD_PID" || true
    EXIT_CODE=$?
    
    echo "[supervisor] run_live.py exited with code $EXIT_CODE at $(date)" | tee -a "$LOG_FILE"
    
    # Rate limit restarts
    now=$(date +%s)
    elapsed=$((now - restart_window_start))
    if [ "$elapsed" -gt 3600 ]; then
        echo "[supervisor] Resetting restart count (1 hour passed)."
        restart_count=0
        restart_window_start=$now
        RESTART_DELAY=5 # Reset delay on successful long run
    fi
    
    restart_count=$((restart_count + 1))
    if [ "$restart_count" -gt "$MAX_RESTARTS_PER_HOUR" ]; then
        echo "[supervisor] ERROR: Too many restarts ($restart_count in ${elapsed}s). Stopping." | tee -a "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
    
    echo "[supervisor] Restarting in ${RESTART_DELAY}s... (attempt $restart_count)" | tee -a "$LOG_FILE"
    sleep "$RESTART_DELAY"
    
    # Exponential backoff
    RESTART_DELAY=$((RESTART_DELAY * 2))
    if [ "$RESTART_DELAY" -gt "$MAX_RESTART_DELAY" ]; then
        RESTART_DELAY=$MAX_RESTART_DELAY
    fi
done
