#!/bin/bash
# ==============================================================================
# Cloud Restart Script for GitHub Codespaces / Cloud Server
# Kills stale processes and restarts both the Dashboard (8585) & noVNC stream (6080)
# ==============================================================================

echo "🧹 Cleaning up existing server & browser processes..."
pkill -9 -f server.py 2>/dev/null || true
pkill -9 -f supervisord 2>/dev/null || true
pkill -9 -f websockify 2>/dev/null || true
pkill -9 -f x11vnc 2>/dev/null || true
pkill -9 -f Xvfb 2>/dev/null || true
sleep 1

# Ensure display directory exists
mkdir -p /tmp/.X11-unix 2>/dev/null || true
chmod 1777 /tmp/.X11-unix 2>/dev/null || true

# Start Xvfb virtual display if installed
if command -v Xvfb >/dev/null 2>&1; then
    echo "🖥️ Starting Xvfb virtual display (:99)..."
    export DISPLAY=:99
    Xvfb :99 -screen 0 1366x768x24 -ac +extension GLX +render -noreset > /dev/null 2>&1 &
    sleep 1
    if command -v x11vnc >/dev/null 2>&1; then
        x11vnc -display :99 -forever -shared -nopw -rfbport 5900 > /dev/null 2>&1 &
    fi
    if command -v websockify >/dev/null 2>&1 && [ -d "/usr/share/novnc" ]; then
        echo "📡 Streaming browser display to noVNC on port 6080..."
        websockify --web /usr/share/novnc 6080 localhost:5900 > /dev/null 2>&1 &
    fi
fi

PYTHON_BIN="python3"
if [ -f "./.venv/bin/python" ]; then
    PYTHON_BIN="./.venv/bin/python"
fi

echo "================================================================="
echo "🚀 Starting AI Dashboard Server on port 8585..."
echo "   Dashboard: http://localhost:8585"
echo "   Live Stream (if noVNC installed): http://localhost:6080"
echo "================================================================="

exec $PYTHON_BIN server.py --port 8585
