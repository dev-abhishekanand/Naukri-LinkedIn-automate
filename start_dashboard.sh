#!/bin/bash
# ==============================================================================
# Master Command Center Quick-Start Script
# Starts the dashboard server on http://localhost:8585
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# Check if port 8585 is already in use
PID=$(lsof -ti :8585 2>/dev/null)
if [ -n "$PID" ]; then
    echo "✓ Master Command Center is already running on PID $PID."
    echo "👉 Open in your browser: http://localhost:8585"
    open "http://localhost:8585" 2>/dev/null || true
    exit 0
fi

PYTHON_BIN="python3"
if [ -f "./.venv/bin/python" ]; then
    PYTHON_BIN="./.venv/bin/python"
fi

echo "🚀 Starting Master Command Center on http://localhost:8585..."
nohup $PYTHON_BIN server.py --port 8585 > /tmp/naukri_dashboard.log 2>&1 &
SERVER_PID=$!
sleep 1

echo "✓ Dashboard active (PID $SERVER_PID)."
echo "👉 Open in your browser: http://localhost:8585"
open "http://localhost:8585" 2>/dev/null || true
