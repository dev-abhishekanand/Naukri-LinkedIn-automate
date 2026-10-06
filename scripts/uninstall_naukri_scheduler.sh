#!/bin/zsh

LABEL="com.naukri.linkedin-ai.naukri"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$TARGET"

echo "Naukri scheduler completely removed from launchd."
echo "Project files, application history, logs, CSVs, sessions, and other runtime data were NOT deleted."
