#!/bin/zsh

LABEL="com.naukri.linkedin-ai.naukri"
PROJECT_DIR="/Users/abhishekanand/Desktop/naukri-linkedin-ai"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ ! -f "$TARGET" ]]; then
    echo "ERROR: Scheduler is not installed."
    echo "Run: scripts/install_naukri_scheduler.sh"
    exit 1
fi

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"

echo "Naukri scheduler resumed."
