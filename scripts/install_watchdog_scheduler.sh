#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_DIR/scheduler_logs"

echo "=== Installing Mac Wake & Power-On Watchdog Scheduler ==="

# 1. Install Watchdog Daemon Plist
WATCHDOG_LABEL="com.naukri.linkedin-ai.watchdog"
cp "$PROJECT_DIR/launchd/$WATCHDOG_LABEL.plist" "$LAUNCH_AGENTS_DIR/$WATCHDOG_LABEL.plist"
launchctl bootout "gui/$(id -u)/$WATCHDOG_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_DIR/$WATCHDOG_LABEL.plist" 2>/dev/null || launchctl load "$LAUNCH_AGENTS_DIR/$WATCHDOG_LABEL.plist" 2>/dev/null || true

# 2. Update and Reload Daily Apply Plist (Daily 09:00 AM Mon-Sun)
NAUKRI_LABEL="com.naukri.linkedin-ai.naukri"
cp "$PROJECT_DIR/launchd/$NAUKRI_LABEL.plist" "$LAUNCH_AGENTS_DIR/$NAUKRI_LABEL.plist"
launchctl bootout "gui/$(id -u)/$NAUKRI_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_DIR/$NAUKRI_LABEL.plist" 2>/dev/null || launchctl load "$LAUNCH_AGENTS_DIR/$NAUKRI_LABEL.plist" 2>/dev/null || true

# 3. Update and Reload Headline Plist (Daily 08:55 AM Mon-Sun)
HEADLINE_LABEL="com.naukri.linkedin-ai.headline"
cp "$PROJECT_DIR/launchd/$HEADLINE_LABEL.plist" "$LAUNCH_AGENTS_DIR/$HEADLINE_LABEL.plist"
launchctl bootout "gui/$(id -u)/$HEADLINE_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_DIR/$HEADLINE_LABEL.plist" 2>/dev/null || launchctl load "$LAUNCH_AGENTS_DIR/$HEADLINE_LABEL.plist" 2>/dev/null || true

# 4. Update and Reload LinkedIn Daily Post Plist (Daily 11:00 AM Mon-Sun)
POST_LABEL="com.naukri.linkedin-ai.post"
cp "$PROJECT_DIR/launchd/$POST_LABEL.plist" "$LAUNCH_AGENTS_DIR/$POST_LABEL.plist"
launchctl bootout "gui/$(id -u)/$POST_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_DIR/$POST_LABEL.plist" 2>/dev/null || launchctl load "$LAUNCH_AGENTS_DIR/$POST_LABEL.plist" 2>/dev/null || true

echo "✓ Watchdog daemon installed and running: $LAUNCH_AGENTS_DIR/$WATCHDOG_LABEL.plist"
echo "✓ Daily 08:55 AM headline schedule active: $LAUNCH_AGENTS_DIR/$HEADLINE_LABEL.plist"
echo "✓ Daily 09:00 AM apply schedule active:    $LAUNCH_AGENTS_DIR/$NAUKRI_LABEL.plist"
echo "✓ Daily 11:00 AM LinkedIn post active:     $LAUNCH_AGENTS_DIR/$POST_LABEL.plist"
echo ""
echo "Watchdog Status:"
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/mac_wake_scheduler.py" --status
