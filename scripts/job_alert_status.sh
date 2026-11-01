#!/usr/bin/env bash
# Check status of Instant Job Alert Monitor daemon on macOS

PLIST_NAME="com.naukri.linkedin-ai.job-alerts.plist"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

echo "=========================================================="
echo "Instant Job Alert Monitor Status"
echo "=========================================================="

if launchctl list | grep -q "com.naukri.linkedin-ai.job-alerts"; then
    echo "Status: [RUNNING / ACTIVE]"
    PID=$(launchctl list | grep "com.naukri.linkedin-ai.job-alerts" | awk '{print $1}')
    EXIT_CODE=$(launchctl list | grep "com.naukri.linkedin-ai.job-alerts" | awk '{print $2}')
    echo "PID: ${PID}"
    echo "Last Exit Code: ${EXIT_CODE}"
else
    echo "Status: [STOPPED / NOT LOADED]"
fi

echo ""
echo "Recent Log Output (last 10 lines):"
echo "----------------------------------------------------------"
if [ -f "${HOME}/Library/Logs/job_alerts.stdout.log" ]; then
    tail -n 10 "${HOME}/Library/Logs/job_alerts.stdout.log"
else
    echo "No log file found yet at ${HOME}/Library/Logs/job_alerts.stdout.log"
fi
