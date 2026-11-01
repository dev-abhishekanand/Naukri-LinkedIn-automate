#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
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

HEADLINE_LOCK="$PROJECT_DIR/.headline.lock"

# 1. Clean up stale lock directories if left over from system sleep or crashes (> 30 mins)
find "$LOCK_DIR" "$HEADLINE_LOCK" -maxdepth 0 -type d -mmin +30 -exec rm -rf {} + 2>/dev/null || true

# 2. Wait up to 3 minutes if morning headline freshness run is currently active BEFORE acquiring lock
MAX_WAIT=180
WAITED=0
while [[ -d "$HEADLINE_LOCK" && $WAITED -lt $MAX_WAIT ]]; do
    echo "[$(date)] Waiting for 8:55 AM headline freshness to complete (.headline.lock active)..." >> "$LOG_FILE"
    sleep 5
    WAITED=$((WAITED + 5))
done

# 3. Acquire exclusive lock for daily apply run
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(date)] Another Naukri run is already active. Exiting." >> "$LOG_FILE"
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 4. Wait for internet connection (up to 30s) in case Mac just woke up from sleep
NET_WAITED=0
while ! curl -s --head --connect-timeout 2 https://www.google.com >/dev/null && [[ $NET_WAITED -lt 30 ]]; do
    echo "[$(date)] Waiting for internet connection to establish after wake..." >> "$LOG_FILE"
    sleep 2
    NET_WAITED=$((NET_WAITED + 2))
done

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

    echo "--- [1/3] Running Naukri Apply (Primary Account) ---"
    "$PYTHON" "$PROJECT_DIR/naukri_apply.py" --unattended --account primary --session session_naukri.json --profile profile.yaml
    NAUKRI_PRIMARY_EXIT=$?
    echo "Naukri Primary finished with exit code: $NAUKRI_PRIMARY_EXIT"

    echo ""
    echo "--- [2/3] Running Naukri Apply (Secondary Account) ---"
    if [[ -f "$PROJECT_DIR/session_naukri_secondary.json" ]]; then
        "$PYTHON" "$PROJECT_DIR/naukri_apply.py" --unattended --account secondary --session session_naukri_secondary.json --profile profile_secondary.yaml
        NAUKRI_SECONDARY_EXIT=$?
        echo "Naukri Secondary finished with exit code: $NAUKRI_SECONDARY_EXIT"
    else
        echo "INFO: session_naukri_secondary.json not found yet. Secondary account skipped for this run."
        NAUKRI_SECONDARY_EXIT=0
    fi

    echo ""
    echo "--- [3/4] Running LinkedIn Apply (Unattended) ---"
    "$PYTHON" "$PROJECT_DIR/linkedin_apply.py" --unattended
    LINKEDIN_EXIT=$?
    echo "LinkedIn finished with exit code: $LINKEDIN_EXIT"

    echo ""
    echo "--- [4/4] Running External Apply Runner (Google Sheet Queue) ---"
    "$PYTHON" "$PROJECT_DIR/external_apply_runner.py" --batch-size 10 --timeout 60
    EXTERNAL_EXIT=$?
    echo "External Apply finished with exit code: $EXTERNAL_EXIT"

    echo "========================================"
    echo "Scheduled run finished: $(date)"
    echo "Naukri Primary: $NAUKRI_PRIMARY_EXIT | Naukri Secondary: $NAUKRI_SECONDARY_EXIT | LinkedIn: $LINKEDIN_EXIT | External: $EXTERNAL_EXIT"
    echo "========================================"

    echo "--- Syncing Daily Apply Metrics to Google Sheets ---"
    "$PYTHON" "$PROJECT_DIR/google_sheets_logger.py" --sync-today
    SYNC_EXIT=$?
    echo "Google Sheets sync exit code: $SYNC_EXIT"

    if [[ ($NAUKRI_PRIMARY_EXIT -eq 0 || $NAUKRI_SECONDARY_EXIT -eq 0) && $SYNC_EXIT -eq 0 ]]; then
        "$PYTHON" -c "
import json, datetime, pathlib
p = pathlib.Path('$PROJECT_DIR/.daily_run_state.json')
data = json.loads(p.read_text()) if p.exists() else {}
data['apply_date'] = datetime.date.today().isoformat()
p.write_text(json.dumps(data, indent=2))
" 2>/dev/null || true
        echo "✓ Apply run and Google Sheets sync verified for today."
    else
        echo "WARN: One or more critical steps failed. Not marking day as complete."
    fi

    if [[ $NAUKRI_PRIMARY_EXIT -ne 0 && $NAUKRI_SECONDARY_EXIT -ne 0 ]]; then
        exit 1
    fi
    exit 0
} >> "$LOG_FILE" 2>&1
