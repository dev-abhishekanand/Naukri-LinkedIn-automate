#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/scheduler_logs"
LOCK_DIR="$PROJECT_DIR/.inbox.lock"

mkdir -p "$LOG_DIR"

if [[ "${1:-}" == "--check" ]]; then
    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi
    echo "Recruiter inbox manager wrapper check OK."
    exit 0
fi

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="$LOG_DIR/inbox_$TIMESTAMP.log"

find "$LOCK_DIR" -maxdepth 0 -type d -mmin +30 -exec rm -rf {} + 2>/dev/null || true

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(date)] Another inbox manager run is already active. Exiting." >> "$LOG_FILE"
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait for internet connection (up to 30s)
NET_WAITED=0
while ! curl -s --head --connect-timeout 2 https://www.google.com >/dev/null && [[ $NET_WAITED -lt 30 ]]; do
    echo "[$(date)] Waiting for internet connection to establish after wake..." >> "$LOG_FILE"
    sleep 2
    NET_WAITED=$((NET_WAITED + 2))
done

{
    echo "========================================"
    echo "Recruiter Inbox Manager & Reply Assistant started: $(date)"
    echo "========================================"

    cd "$PROJECT_DIR" || exit 1

    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi

    "$PYTHON" "$PROJECT_DIR/recruiter_inbox_manager.py"
    EXIT_CODE=$?

    echo "========================================"
    echo "Recruiter inbox check finished with exit code: $EXIT_CODE at $(date)"
    echo "========================================"
    exit $EXIT_CODE
} >> "$LOG_FILE" 2>&1
