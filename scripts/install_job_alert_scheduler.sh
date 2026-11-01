#!/usr/bin/env bash
# Install & activate the Instant Job Alert Monitor launchd daemon on macOS

PLIST_NAME="com.naukri.linkedin-ai.job-alerts.plist"
SOURCE_PLIST="/Users/abhishekanand/Desktop/naukri-linkedin-ai/launchd/${PLIST_NAME}"
TARGET_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${TARGET_DIR}/${PLIST_NAME}"

echo "=========================================================="
echo "Installing macOS Instant Job Alert Monitor Daemon"
echo "=========================================================="

mkdir -p "${TARGET_DIR}"
mkdir -p "${HOME}/Library/Logs"

# Unload existing if currently active
if launchctl list | grep -q "com.naukri.linkedin-ai.job-alerts"; then
    echo "Unloading existing job-alerts daemon..."
    launchctl unload "${TARGET_PLIST}" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
echo "Copying plist to ${TARGET_PLIST}..."
cp -f "${SOURCE_PLIST}" "${TARGET_PLIST}"

# Load and start daemon
echo "Loading launchd daemon..."
launchctl load -w "${TARGET_PLIST}"

sleep 1

# Check status
if launchctl list | grep -q "com.naukri.linkedin-ai.job-alerts"; then
    echo "[✓] Instant Job Alert Monitor successfully installed and running!"
    echo "    Interval: Every 15 minutes"
    echo "    Notifications: Native macOS Banner with chime"
    echo "    Log File: ${HOME}/Library/Logs/job_alerts.stdout.log"
else
    echo "[!] Warning: Daemon loaded but not appearing in launchctl list."
fi
