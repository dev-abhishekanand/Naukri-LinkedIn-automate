#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/scheduler_logs"
LOCK_DIR="$PROJECT_DIR/.linkedin_matched_jobs.lock"

mkdir -p "$LOG_DIR"

if [[ "${1:-}" == "--check" ]]; then
    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi
    echo "LinkedIn matched jobs runner check OK."
    exit 0
fi

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="$LOG_DIR/linkedin_matched_jobs_$TIMESTAMP.log"

find "$LOCK_DIR" -maxdepth 0 -type d -mmin +45 -exec rm -rf {} + 2>/dev/null || true

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(date)] Another LinkedIn matched jobs run is already active. Exiting." | tee -a "$LOG_FILE"
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait for internet connection (up to 30s) in case Mac just woke up
NET_WAITED=0
while ! curl -s --head --connect-timeout 2 https://www.google.com >/dev/null && [[ $NET_WAITED -lt 30 ]]; do
    echo "[$(date)] Waiting for internet connection..." >> "$LOG_FILE"
    sleep 2
    NET_WAITED=$((NET_WAITED + 2))
done

{
    echo "========================================"
    echo "LinkedIn Matched Profile Jobs Auto-Apply started: $(date)"
    echo "========================================"

    cd "$PROJECT_DIR" || exit 1

    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi

    # Pass any extra arguments (e.g. --dry-run, --max-jobs)
    "$PYTHON" linkedin_matched_jobs_apply.py "$@"
    EXIT_CODE=$?

    echo "========================================"
    echo "LinkedIn Matched Profile Jobs finished: $(date) (Exit Code: $EXIT_CODE)"
    echo "========================================"
    exit $EXIT_CODE
} 2>&1 | tee -a "$LOG_FILE"
