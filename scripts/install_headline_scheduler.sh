#!/bin/zsh

LABEL="com.naukri.linkedin-ai.headline"
PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
SOURCE="$PROJECT_DIR/launchd/$LABEL.plist"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$PROJECT_DIR/scheduler_logs"

cp "$SOURCE" "$TARGET"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"

echo "Naukri daily headline update scheduler installed and loaded."
echo "Schedule: Every day (Monday to Sunday) at 09:30 AM IST."
echo "Plist: $TARGET"
