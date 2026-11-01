#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/scheduler_logs"
POST_LOCK="$PROJECT_DIR/.post.lock"
APPLY_LOCK="$PROJECT_DIR/.scheduler.lock"

mkdir -p "$LOG_DIR"

if [[ "${1:-}" == "--check" ]]; then
    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi
    echo "Post scheduler wrapper check OK."
    echo "Project: $PROJECT_DIR"
    echo "Python:  $PYTHON"
    echo "Logs:    $LOG_DIR"
    exit 0
fi

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="$LOG_DIR/post_$TIMESTAMP.log"

# 1. Clean up stale locks (> 30 mins)
find "$POST_LOCK" "$APPLY_LOCK" -maxdepth 0 -type d -mmin +30 -exec rm -rf {} + 2>/dev/null || true

# 2. If apply job (.scheduler.lock) is active, wait up to 5 minutes BEFORE acquiring lock
MAX_WAIT=300
WAITED=0
while [[ -d "$APPLY_LOCK" && $WAITED -lt $MAX_WAIT ]]; do
    echo "[$(date)] Waiting for apply job to finish (.scheduler.lock active)..." >> "$LOG_FILE"
    sleep 10
    WAITED=$((WAITED + 10))
done

if [[ -d "$APPLY_LOCK" ]]; then
    echo "[$(date)] Apply job is still actively running after ${MAX_WAIT}s. Deferring LinkedIn post to prevent browser profile collision." >> "$LOG_FILE"
    exit 0
fi

# 3. Acquire exclusive lock for LinkedIn post
if ! mkdir "$POST_LOCK" 2>/dev/null; then
    echo "[$(date)] Another LinkedIn post run is already active. Exiting." >> "$LOG_FILE"
    exit 0
fi

cleanup() {
    rmdir "$POST_LOCK" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 4. Wait for internet connection (up to 30s)
NET_WAITED=0
while ! curl -s --head --connect-timeout 2 https://www.google.com >/dev/null && [[ $NET_WAITED -lt 30 ]]; do
    echo "[$(date)] Waiting for internet connection to establish after wake..." >> "$LOG_FILE"
    sleep 2
    NET_WAITED=$((NET_WAITED + 2))
done

{
    echo "========================================"
    echo "LinkedIn daily technical post started: $(date)"
    echo "========================================"

    cd "$PROJECT_DIR" || {
        echo "ERROR: Could not change to project directory."
        exit 1
    }

    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi

    # Run daily post generator and publisher unattended
    "$PYTHON" "$PROJECT_DIR/linkedin_daily_post.py" --unattended
    POST_EXIT=$?

    echo "========================================"
    echo "LinkedIn post finished at $(date)"
    echo "  Exit Code: $POST_EXIT"
    echo "========================================"

    if [[ $POST_EXIT -ne 0 ]]; then
        exit 1
    fi
    exit 0
} >> "$LOG_FILE" 2>&1
