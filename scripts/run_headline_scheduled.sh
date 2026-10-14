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

# If another headline run is somehow already active, exit immediately
if ! mkdir "$HEADLINE_LOCK" 2>/dev/null; then
    echo "[$(date)] Another headline update run is already active. Exiting." >> "$LOG_FILE"
    exit 0
fi

cleanup() {
    rmdir "$HEADLINE_LOCK" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait up to 10 minutes (40 x 15s) if morning apply job (.scheduler.lock) is active
MAX_WAIT_SECONDS=600
WAITED=0
while [[ -d "$SCHEDULER_LOCK" && $WAITED -lt $MAX_WAIT_SECONDS ]]; do
    echo "[$(date)] Waiting for daily application run to finish (.scheduler.lock active)..." >> "$LOG_FILE"
    sleep 15
    WAITED=$((WAITED + 15))
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
    echo "[1/3] Updating Naukri profile headline..."
    "$PYTHON" "$PROJECT_DIR/naukri_update_headline.py" --unattended
    HEADLINE_EXIT=$?

    # Step 2: Re-upload Resume (sets "Resume uploaded: Today" & 100% freshness on Naukri)
    echo "[2/3] Re-uploading resume to Naukri..."
    "$PYTHON" "$PROJECT_DIR/naukri_refresh_resume.py" --unattended
    RESUME_EXIT=$?

    # Step 3: Rotate LinkedIn Profile Headline (elevates Recruiter search & activity signals)
    echo "[3/3] Updating LinkedIn profile headline..."
    "$PYTHON" "$PROJECT_DIR/linkedin_update_headline.py" --unattended
    LINKEDIN_EXIT=$?

    echo "========================================"
    echo "Daily refresh finished at $(date)"
    echo "  Naukri Headline Exit Code: $HEADLINE_EXIT"
    echo "  Naukri Resume Exit Code:   $RESUME_EXIT"
    echo "  LinkedIn Headline Exit:    $LINKEDIN_EXIT"
    echo "========================================"

    if [[ $HEADLINE_EXIT -ne 0 || $RESUME_EXIT -ne 0 || $LINKEDIN_EXIT -ne 0 ]]; then
        exit 1
    fi
    exit 0
} >> "$LOG_FILE" 2>&1
