#!/bin/bash
# Trigger Jarvis via SIGUSR1 — bind this to Super+J in Hyprland
# Usage: ~/.config/hypr/scripts/jarvis-trigger.sh
PID_FILE="/tmp/jarvis.pid"
if [[ ! -f "$PID_FILE" ]]; then
    echo "Jarvis is not running (no PID file at $PID_FILE)" >&2
    exit 1
fi
pid=$(cat "$PID_FILE")
if ! kill -0 "$pid" 2>/dev/null; then
    echo "Jarvis process $pid is not alive — removing stale PID file" >&2
    rm -f "$PID_FILE"
    exit 1
fi
kill -SIGUSR1 "$pid"
