#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/Desktop/naukri-linkedin-ai"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/scheduler_logs"
LOCK_DIR="$PROJECT_DIR/.scheduler.lock"

mkdir -p "$LOG_DIR"

if [[ "${1:-}" == "--check" ]]; then
    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi
    echo "Scheduler wrapper check OK."
    echo "Project: $PROJECT_DIR"
    echo "Python:  $PYTHON"
    echo "Logs:    $LOG_DIR"
    exit 0
fi

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="$LOG_DIR/naukri_$TIMESTAMP.log"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(date)] Another Naukri run is already active. Exiting." >> "$LOG_FILE"
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

{
    echo "========================================"
    echo "Naukri scheduled run started: $(date)"
    echo "========================================"

    cd "$PROJECT_DIR" || {
        echo "ERROR: Could not change to project directory."
        exit 1
    }

    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi

    "$PYTHON" "$PROJECT_DIR/naukri_apply.py"
    EXIT_CODE=$?

    echo "========================================"
    echo "Naukri scheduled run finished: $(date)"
    echo "Exit code: $EXIT_CODE"
    echo "========================================"

    exit "$EXIT_CODE"
} >> "$LOG_FILE" 2>&1
