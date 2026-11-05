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
    echo "Stopping existing server on PID $PID to reload fresh code..."
    kill -9 $PID 2>/dev/null || true
    sleep 1
fi

PYTHON_BIN="python3"
if [ -f "./.venv/bin/python" ]; then
    PYTHON_BIN="./.venv/bin/python"
fi

# Detect local network IP for mobile device access
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="127.0.0.1"
fi

echo "🚀 Starting Master Command Center on http://localhost:8585..."
nohup $PYTHON_BIN -u server.py --port 8585 > /tmp/naukri_dashboard.log 2>&1 &
SERVER_PID=$!
sleep 1

echo "=================================================================="
echo "✓ Dashboard active (PID $SERVER_PID)."
echo "👉 Laptop Browser:       http://localhost:8585"
echo "👉 Phone / Tablet:       http://${LOCAL_IP}:8585"
echo ""
echo "📲 On your iPhone or Android:"
echo "   1. Open Safari or Chrome on your phone."
echo "   2. Visit: http://${LOCAL_IP}:8585 (same Wi-Fi)."
echo "   3. Tap 'Share' ➔ 'Add to Home Screen' to install as Web App!"
echo "=================================================================="

open "http://localhost:8585" 2>/dev/null || true
