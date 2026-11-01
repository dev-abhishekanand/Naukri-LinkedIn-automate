#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/scheduler_logs"
HEADLINE_LOCK="$PROJECT_DIR/.headline.lock"
SCHEDULER_LOCK="$PROJECT_DIR/.scheduler.lock"

mkdir -p "$LOG_DIR"

if [[ "${1:-}" == "--check" ]]; then
    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi
    echo "Headline scheduler wrapper check OK."
    echo "Project: $PROJECT_DIR"
    echo "Python:  $PYTHON"
    echo "Logs:    $LOG_DIR"
    exit 0
fi

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="$LOG_DIR/headline_$TIMESTAMP.log"

# 1. Clean up stale locks (> 30 mins)
find "$HEADLINE_LOCK" "$SCHEDULER_LOCK" -maxdepth 0 -type d -mmin +30 -exec rm -rf {} + 2>/dev/null || true

# 2. Wait up to 5 minutes if morning apply job (.scheduler.lock) is active BEFORE acquiring lock
MAX_WAIT_SECONDS=300
WAITED=0
while [[ -d "$SCHEDULER_LOCK" && $WAITED -lt $MAX_WAIT_SECONDS ]]; do
    echo "[$(date)] Waiting for daily application run to finish (.scheduler.lock active)..." >> "$LOG_FILE"
    sleep 5
    WAITED=$((WAITED + 5))
done

# 3. Acquire exclusive lock for headline update
if ! mkdir "$HEADLINE_LOCK" 2>/dev/null; then
    echo "[$(date)] Another headline update run is already active. Exiting." >> "$LOG_FILE"
    exit 0
fi

cleanup() {
    rmdir "$HEADLINE_LOCK" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 4. Wait for internet connection (up to 30s) in case Mac just woke up
NET_WAITED=0
while ! curl -s --head --connect-timeout 2 https://www.google.com >/dev/null && [[ $NET_WAITED -lt 30 ]]; do
    echo "[$(date)] Waiting for internet connection to establish after wake..." >> "$LOG_FILE"
    sleep 2
    NET_WAITED=$((NET_WAITED + 2))
done

{
    echo "========================================"
    echo "Naukri daily refresh started: $(date)"
    echo "========================================"

    cd "$PROJECT_DIR" || {
        echo "ERROR: Could not change to project directory."
        exit 1
    }

    if [[ ! -x "$PYTHON" ]]; then
        echo "ERROR: Python executable not found: $PYTHON"
        exit 1
    fi

    # Step 1: Rotate Profile Headline (sets "Updated: Today" on Naukri)
    echo "[1/4] Updating Naukri primary profile headline..."
    "$PYTHON" "$PROJECT_DIR/naukri_update_headline.py" --unattended --account primary --session session_naukri.json --profile profile.yaml
    HEADLINE_EXIT=$?

    echo "[2/4] Updating Naukri secondary profile headline..."
    if [[ -f "$PROJECT_DIR/session_naukri_secondary.json" ]]; then
        "$PYTHON" "$PROJECT_DIR/naukri_update_headline.py" --unattended --account secondary --session session_naukri_secondary.json --profile profile_secondary.yaml
    else
        echo "INFO: session_naukri_secondary.json not found yet."
    fi

    # Step 2: Re-upload Resume (sets "Resume uploaded: Today" & 100% freshness on Naukri)
    echo "[3/5] Re-uploading resume to Naukri (Primary)..."
    "$PYTHON" "$PROJECT_DIR/naukri_refresh_resume.py" --unattended --account primary --session session_naukri.json --profile profile.yaml
    RESUME_PRIMARY_EXIT=$?

    echo "[4/5] Re-uploading resume to Naukri (Secondary)..."
    if [[ -f "$PROJECT_DIR/session_naukri_secondary.json" ]]; then
        "$PYTHON" "$PROJECT_DIR/naukri_refresh_resume.py" --unattended --account secondary --session session_naukri_secondary.json --profile profile_secondary.yaml
        RESUME_SECONDARY_EXIT=$?
    else
        RESUME_SECONDARY_EXIT=0
    fi

    # Step 3: Rotate LinkedIn Profile Headline (elevates Recruiter search & activity signals)
    echo "[5/5] Updating LinkedIn profile headline..."
    "$PYTHON" "$PROJECT_DIR/linkedin_update_headline.py" --unattended
    LINKEDIN_EXIT=$?

    echo "========================================"
    echo "Daily refresh finished at $(date)"
    echo "  Naukri Primary Headline Exit:  $HEADLINE_EXIT"
    echo "  Naukri Primary Resume Exit:    $RESUME_PRIMARY_EXIT"
    echo "  Naukri Secondary Resume Exit:  $RESUME_SECONDARY_EXIT"
    echo "  LinkedIn Headline Exit:        $LINKEDIN_EXIT"
    echo "========================================"

    if [[ $HEADLINE_EXIT -eq 0 && $RESUME_PRIMARY_EXIT -eq 0 ]]; then
        "$PYTHON" -c "
import json, datetime, pathlib
p = pathlib.Path('$PROJECT_DIR/.daily_run_state.json')
data = json.loads(p.read_text()) if p.exists() else {}
data['headline_date'] = datetime.date.today().isoformat()
p.write_text(json.dumps(data, indent=2))
" 2>/dev/null || true
    fi

    if [[ $HEADLINE_EXIT -ne 0 || $RESUME_PRIMARY_EXIT -ne 0 ]]; then
        exit 1
    fi
    exit 0
} >> "$LOG_FILE" 2>&1
