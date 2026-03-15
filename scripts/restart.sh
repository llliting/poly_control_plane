#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/poly_control_plane}"
PORT="${PORT:-8090}"

cd "$REPO_DIR"
mkdir -p logs

echo "pulling latest..."
git pull

echo "stopping uvicorn..."
pkill -f "uvicorn app.main:app" || true
sleep 1

# verify stopped
if pgrep -af "uvicorn app.main:app" > /dev/null 2>&1; then
  echo "WARNING: uvicorn still running, force killing..."
  pkill -9 -f "uvicorn app.main:app" || true
  sleep 1
fi

echo "starting uvicorn on port $PORT..."
source .venv/bin/activate
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" > logs/uvicorn.out 2>&1 &
echo $! > logs/uvicorn.pid
disown

sleep 2

# health check
if curl -sf "http://127.0.0.1:${PORT}/healthz" > /dev/null 2>&1; then
  echo "OK — control plane running (pid $(cat logs/uvicorn.pid), port $PORT)"
else
  echo "WARNING — health check failed, check logs/uvicorn.out"
  tail -20 logs/uvicorn.out
fi
