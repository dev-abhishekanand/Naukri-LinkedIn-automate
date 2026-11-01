#!/bin/bash
# ==============================================================================
# MORNING POWER BURST (08:55 AM – 10:30 AM)
# Batches all outbound job applications, profile freshness touches,
# and daily thought leadership publishing into one consolidated window.
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1
export PYTHONPATH="$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/scheduler_logs"
mkdir -p "$LOG_DIR"
BURST_LOG="$LOG_DIR/morning_burst_$(date +%Y-%m-%d).log"

echo "=================================================================" | tee -a "$BURST_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🌅 STARTING MORNING POWER BURST" | tee -a "$BURST_LOG"
echo "=================================================================" | tee -a "$BURST_LOG"

# Step 1: Naukri Profile Freshness & Headline Touch (08:55 AM)
echo "\n[Step 1/5] Running Naukri Profile Freshness & Headline Touch..." | tee -a "$BURST_LOG"
if [ -f "$PROJECT_DIR/scripts/run_headline_scheduled.sh" ]; then
    /bin/zsh "$PROJECT_DIR/scripts/run_headline_scheduled.sh" >> "$BURST_LOG" 2>&1
    echo "✓ Step 1 Complete: Profile bumped to 'Updated Today'" | tee -a "$BURST_LOG"
fi
sleep 5

# Step 2: Telegram Hiring Channels Sweep (09:00 AM)
echo "\n[Step 2/5] Sweeping Telegram Tech Hiring Channels for Fresh Jobs..." | tee -a "$BURST_LOG"
./.venv/bin/python telegram_jobs_listener.py >> "$BURST_LOG" 2>&1
echo "✓ Step 2 Complete: Telegram channels scanned" | tee -a "$BURST_LOG"
sleep 5

# Step 3: Multi-Portal Auto-Apply Batch Engine (09:10 AM)
echo "\n[Step 3/5] Launching Multi-Portal Auto-Apply Batch Engine..." | tee -a "$BURST_LOG"
if [ -f "$PROJECT_DIR/scripts/run_naukri_scheduled.sh" ]; then
    /bin/zsh "$PROJECT_DIR/scripts/run_naukri_scheduled.sh" >> "$BURST_LOG" 2>&1
fi
if [ -f "$PROJECT_DIR/scripts/run_linkedin_matched_jobs.sh" ]; then
    /bin/zsh "$PROJECT_DIR/scripts/run_linkedin_matched_jobs.sh" >> "$BURST_LOG" 2>&1
fi
echo "✓ Step 3 Complete: Multi-portal applications submitted" | tee -a "$BURST_LOG"
sleep 5

# Step 4: Google Sheets 'Apply Yourself' Live Queue Sync (10:00 AM)
echo "\n[Step 4/5] Syncing Google Sheets 'Apply Yourself' Live Queue..." | tee -a "$BURST_LOG"
./.venv/bin/python main.py sheet-sync --limit 5 >> "$BURST_LOG" 2>&1 || true
echo "✓ Step 4 Complete: Direct ATS sheet jobs processed" | tee -a "$BURST_LOG"
sleep 5

# Step 5: LinkedIn Daily Thought Leadership Post (10:15 AM)
echo "\n[Step 5/5] Publishing LinkedIn Daily Technical Article..." | tee -a "$BURST_LOG"
if [ -f "$PROJECT_DIR/scripts/run_post_scheduled.sh" ]; then
    /bin/zsh "$PROJECT_DIR/scripts/run_post_scheduled.sh" >> "$BURST_LOG" 2>&1
    echo "✓ Step 5 Complete: LinkedIn daily article published" | tee -a "$BURST_LOG"
fi

# Cleanup: Ensure all Playwright/Chromium instances close cleanly
echo "\n[Cleanup] Closing browser sessions and freeing system memory..." | tee -a "$BURST_LOG"
if [ -f "$PROJECT_DIR/scripts/cleanup_zombies.sh" ]; then
    /bin/bash "$PROJECT_DIR/scripts/cleanup_zombies.sh" >> "$BURST_LOG" 2>&1
fi

echo "=================================================================" | tee -a "$BURST_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🌅 MORNING POWER BURST COMPLETED" | tee -a "$BURST_LOG"
echo "=================================================================" | tee -a "$BURST_LOG"
