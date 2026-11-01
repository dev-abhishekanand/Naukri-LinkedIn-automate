#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
PYTHON="$PROJECT_DIR/.venv/bin/python"
PORT=8585

# Check if dashboard server is already running on port 8585
if ! lsof -i :"$PORT" >/dev/null 2>&1; then
    echo "Starting Diagnostics Web Dashboard on http://localhost:$PORT..."
    cd "$PROJECT_DIR" || exit 1
    nohup "$PYTHON" "$PROJECT_DIR/scripts/diagnostics_dashboard.py" --port "$PORT" >/dev/null 2>&1 &
    sleep 1.2
fi

echo "Opening Dashboard in default browser: http://localhost:$PORT"
open "http://localhost:$PORT"
