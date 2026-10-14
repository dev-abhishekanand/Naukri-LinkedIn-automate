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

if ! mkdir "$POST_LOCK" 2>/dev/null; then
    echo "[$(date)] Another LinkedIn post run is already active. Exiting." >> "$LOG_FILE"
    exit 0
fi

cleanup() {
    rmdir "$POST_LOCK" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait up to 5 minutes if morning apply job (.scheduler.lock) is active
MAX_WAIT=300
WAITED=0
while [[ -d "$APPLY_LOCK" && $WAITED -lt $MAX_WAIT ]]; do
    echo "[$(date)] Waiting for apply job to finish (.scheduler.lock active)..." >> "$LOG_FILE"
    sleep 15
    WAITED=$((WAITED + 15))
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
