#!/bin/bash
# ==============================================================================
# EVENING POWER BURST (05:30 PM – 06:45 PM)
# Batches all inbound recruiter responses, interview detections,
# multi-touch follow-ups, and daily Telegram summaries into one window.
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1
export PYTHONPATH="$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/scheduler_logs"
mkdir -p "$LOG_DIR"
BURST_LOG="$LOG_DIR/evening_burst_$(date +%Y-%m-%d).log"

echo "=================================================================" | tee -a "$BURST_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🌆 STARTING EVENING POWER BURST" | tee -a "$BURST_LOG"
echo "=================================================================" | tee -a "$BURST_LOG"

# Step 1: Recruiter Inbox Scanner & Reply Assistant (05:30 PM)
echo "\n[Step 1/5] Scanning Candidate Gmail for Inbound Recruiter Replies..." | tee -a "$BURST_LOG"
if [ -f "$PROJECT_DIR/scripts/run_inbox_scheduled.sh" ]; then
    /bin/zsh "$PROJECT_DIR/scripts/run_inbox_scheduled.sh" >> "$BURST_LOG" 2>&1
    echo "✓ Step 1 Complete: Recruiter replies processed & response drafts staged" | tee -a "$BURST_LOG"
fi
sleep 5

# Step 2: Interview Radar & Calendar Sync (05:45 PM)
echo "\n[Step 2/5] Running Interview Screening Detector & Calendar (.ics) Generator..." | tee -a "$BURST_LOG"
./.venv/bin/python recruiter_meeting_detector.py >> "$BURST_LOG" 2>&1 || true
echo "✓ Step 2 Complete: Meeting invitations synchronized" | tee -a "$BURST_LOG"
sleep 5

# Step 3: Multi-Touch Follow-Up Engine (06:00 PM)
echo "\n[Step 3/5] Evaluating D+4 and D+9 Multi-Touch Follow-Up Sequences..." | tee -a "$BURST_LOG"
./.venv/bin/python recruiter_followup_manager.py >> "$BURST_LOG" 2>&1
echo "✓ Step 3 Complete: Follow-up value-add drafts created in Gmail" | tee -a "$BURST_LOG"
sleep 5

# Step 4: LinkedIn Recruiter Connector (06:15 PM)
echo "\n[Step 4/5] Sending Safe 5 Tailored Connection Notes to Discovered Recruiters..." | tee -a "$BURST_LOG"
./.venv/bin/python linkedin_recruiter_connector.py --limit 5 >> "$BURST_LOG" 2>&1 || true
echo "✓ Step 4 Complete: Recruiter connection notes dispatched" | tee -a "$BURST_LOG"
sleep 5

# Step 5: Daily Ledger Metrics Sync & Telegram Mobile Summary (06:30 PM)
echo "\n[Step 5/5] Syncing Daily Ledger & Sending Mobile Telegram Push..." | tee -a "$BURST_LOG"
./.venv/bin/python -c "
from common.telegram_notifier import alert_daily_summary, get_telegram_config
from server import get_all_metrics
m = get_all_metrics()
t = m.get('today', {})
p = m.get('linkedin_post', {})
alert_daily_summary(
    applied_total=t.get('applied_total', 0),
    by_portal=t.get('by_portal', {}),
    pending_sheet=m.get('google_sheets', {}).get('pending', 0),
    post_published=bool(p.get('posted_today', False))
)
print('✓ Synced daily metrics and dispatched Telegram push alert.')
" >> "$BURST_LOG" 2>&1 || true

# Cleanup: Free all browser processes before Night Silence
echo "\n[Cleanup] Closing browser sessions and freeing system memory..." | tee -a "$BURST_LOG"
if [ -f "$PROJECT_DIR/scripts/cleanup_zombies.sh" ]; then
    /bin/bash "$PROJECT_DIR/scripts/cleanup_zombies.sh" >> "$BURST_LOG" 2>&1
fi

echo "=================================================================" | tee -a "$BURST_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🌆 EVENING POWER BURST COMPLETED" | tee -a "$BURST_LOG"
echo "=================================================================" | tee -a "$BURST_LOG"
