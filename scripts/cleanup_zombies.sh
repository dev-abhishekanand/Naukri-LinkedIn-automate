#!/bin/bash
# ==============================================================================
# Zombie Browser Process & Memory Safeguard
# Kills orphaned Chromium / Chrome Helper processes that were orphaned when
# automation subshells crashed or were stopped.
# ==============================================================================

echo "🧹 Checking for orphaned Playwright / Chrome processes..."

# Kill orphaned Google Chrome Helper processes with PPID 1 that consume background CPU
ORPHANS=$(ps -ef | grep -E "Google Chrome Helper|chromium|playwright" | grep -v grep | awk '$3 == 1 {print $2}')

if [ -n "$ORPHANS" ]; then
    echo "⚠️ Found orphaned browser processes: $ORPHANS"
    echo "$ORPHANS" | xargs kill -9 2>/dev/null || true
    echo "✓ Cleaned up orphaned browser processes."
else
    echo "✓ No orphaned browser processes found. Memory & CPU are clean."
fi
