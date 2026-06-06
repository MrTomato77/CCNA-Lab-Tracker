#!/usr/bin/env bash
# Linux/macOS counterpart of stop.bat. Locates the process listening
# on :8080 and sends SIGTERM (fall back to SIGKILL if it doesn't exit).

set -e
cd "$(dirname "$0")"

# Read PORT from .env (falls back to 8080). Must mirror app.py's default.
PORT=8080
if [ -f .env ]; then
    env_port=$(grep -E '^PORT=' .env | tail -1 | cut -d= -f2 | tr -d '[:space:]')
    [ -n "$env_port" ] && PORT=$env_port
fi

echo "  Stopping server on port $PORT..."

PID=""
if command -v lsof >/dev/null 2>&1; then
    PID=$(lsof -t -i ":$PORT" -sTCP:LISTEN 2>/dev/null || true)
elif command -v ss >/dev/null 2>&1; then
    PID=$(ss -ltnp "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K\d+' | head -1 || true)
fi

if [ -z "$PID" ]; then
    echo "  [INFO] No process found on port $PORT."
    exit 0
fi

kill "$PID" 2>/dev/null || true
sleep 1
if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID" 2>/dev/null || true
fi
echo "  [OK] Stopped (PID: $PID)."
