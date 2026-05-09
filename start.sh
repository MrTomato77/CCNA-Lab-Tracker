#!/usr/bin/env bash
# Linux/macOS counterpart of start.bat. Same behaviour: verify deps,
# warn if port 8080 is taken, open the browser, then run app.py.

set -e
cd "$(dirname "$0")"

echo
echo "  ====================================================="
echo "    CCNA Lab Tracker"
echo "  ====================================================="
echo

# Check port 8080 not in use. lsof is on most distros / macOS; fall
# back to ss for minimal containers.
if command -v lsof >/dev/null 2>&1; then
    if lsof -i :8080 -sTCP:LISTEN >/dev/null 2>&1; then
        echo "  [WARN] Port 8080 is already in use."
        echo "  Run ./stop.sh first, then try again."
        exit 1
    fi
elif command -v ss >/dev/null 2>&1; then
    if ss -ltn 'sport = :8080' | grep -q LISTEN; then
        echo "  [WARN] Port 8080 is already in use."
        echo "  Run ./stop.sh first, then try again."
        exit 1
    fi
fi

# Check Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "  [ERROR] python3 not found. Install Python 3.11+ from your"
    echo "  package manager or python.org."
    exit 1
fi

# Create venv on first run, activate every run.
if [ ! -d venv ]; then
    echo "  [INFO] Creating venv..."
    python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

echo "  [INFO] Verifying dependencies..."
pip install -q -r requirements.txt --disable-pip-version-check

# Open browser after 2s; ignore errors if no browser available (headless).
( sleep 2 && (xdg-open http://localhost:8080 || open http://localhost:8080) >/dev/null 2>&1 ) &

python app.py
