#!/usr/bin/env bash
# Linux/macOS counterpart of stop.bat. Locates the process listening
# on :8080 and sends SIGTERM (fall back to SIGKILL if it doesn't exit).

set -e

echo "  Stopping server on port 8080..."

PID=""
if command -v lsof >/dev/null 2>&1; then
    PID=$(lsof -t -i :8080 -sTCP:LISTEN 2>/dev/null || true)
elif command -v ss >/dev/null 2>&1; then
    PID=$(ss -ltnp 'sport = :8080' 2>/dev/null | grep -oP 'pid=\K\d+' | head -1 || true)
fi

if [ -z "$PID" ]; then
    echo "  [INFO] No process found on port 8080."
    exit 0
fi

kill "$PID" 2>/dev/null || true
sleep 1
if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID" 2>/dev/null || true
fi
echo "  [OK] Stopped (PID: $PID)."
