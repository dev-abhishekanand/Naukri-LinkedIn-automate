#!/bin/zsh

PLIST_NAME="com.naukri.linkedin-ai.post.plist"
SRC_PLIST="/Users/abhishekanand/naukri-linkedin-ai/launchd/$PLIST_NAME"
DEST_PLIST="$HOME/Library/LaunchAgents/$PLIST_NAME"

if [[ ! -f "$SRC_PLIST" ]]; then
    echo "ERROR: Source plist not found at $SRC_PLIST"
    exit 1
fi

echo "Installing LinkedIn daily post scheduler to $DEST_PLIST..."
cp "$SRC_PLIST" "$DEST_PLIST"

# Unload if currently loaded
launchctl unload "$DEST_PLIST" 2>/dev/null || true

# Load the new plist
launchctl load "$DEST_PLIST"

echo "✓ LinkedIn daily post scheduler installed and loaded successfully."
echo "  Scheduled to run every day (Mon-Sun) at 10:00 AM IST."
launchctl list | grep "com.naukri.linkedin-ai.post"
