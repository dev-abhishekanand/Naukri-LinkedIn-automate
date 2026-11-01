#!/bin/zsh

PROJECT_DIR="/Users/abhishekanand/naukri-linkedin-ai"
PYTHON="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR" || exit 1
"$PYTHON" "$PROJECT_DIR/scripts/automation_diagnostics.py"
