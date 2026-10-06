#!/bin/zsh

LABEL="com.naukri.linkedin-ai.naukri"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "=== Naukri Scheduler Status ==="

if [[ -f "$TARGET" ]]; then
    echo "Installed: YES"
else
    echo "Installed: NO"
fi

if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
    echo "Loaded: YES"
else
    echo "Loaded: NO"
fi
