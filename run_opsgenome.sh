#!/usr/bin/env bash
set -e

# OpsGenome Launcher
export PYTHONPATH="${PYTHONPATH}:."

# Check if port 8765 is already occupied and terminate previous instance
EXISTING_PID=$(lsof -ti :8765 2>/dev/null || true)
if [ -n "$EXISTING_PID" ]; then
    echo "Notice: Found existing process ($EXISTING_PID) on port 8765. Stopping previous instance..."
    kill -9 $EXISTING_PID 2>/dev/null || true
    sleep 1
fi

# Run daemon
exec python3 -m opsgenome.cli.main daemon --host 127.0.0.1 --port 8765

