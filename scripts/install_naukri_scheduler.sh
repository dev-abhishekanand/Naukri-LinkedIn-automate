#!/bin/zsh

LABEL="com.naukri.linkedin-ai.naukri"
PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
SOURCE="$PROJECT_DIR/launchd/$LABEL.plist"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$PROJECT_DIR/scheduler_logs"

cp "$SOURCE" "$TARGET"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"

echo "Naukri + LinkedIn auto-apply scheduler installed and loaded."
echo "Schedule: Monday-Friday at 09:00."
echo "Plist: $TARGET"
