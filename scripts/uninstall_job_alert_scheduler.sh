#!/usr/bin/env bash
# Uninstall & deactivate the Instant Job Alert Monitor daemon on macOS

PLIST_NAME="com.naukri.linkedin-ai.job-alerts.plist"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

echo "=========================================================="
echo "Uninstalling macOS Instant Job Alert Monitor Daemon"
echo "=========================================================="

if [ -f "${TARGET_PLIST}" ]; then
    echo "Unloading daemon..."
    launchctl unload "${TARGET_PLIST}" 2>/dev/null || true
    echo "Removing plist file from LaunchAgents..."
    rm -f "${TARGET_PLIST}"
    echo "[✓] Instant Job Alert Monitor successfully uninstalled."
else
    echo "Daemon was not installed at ${TARGET_PLIST}."
fi
