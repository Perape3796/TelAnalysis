#!/usr/bin/env bash
#
# TelAnalysis launcher — one command, fully local.
#
# Builds the React frontend (first run only) and starts the FastAPI server,
# which serves both the API and the built SPA same-origin on 127.0.0.1:8000.
# Your chat export is read from a local path and never leaves the machine.
#
# Usage:  ./run.sh [--rebuild] [PORT]
#
set -euo pipefail
cd "$(dirname "$0")"

PORT=8000
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    [0-9]*) PORT="$arg" ;;
  esac
done

# Pick a Python interpreter (prefer the project venv).
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

# Build the frontend if it hasn't been built (or when --rebuild is passed).
if [ "$REBUILD" = "1" ] || [ ! -f "frontend/dist/index.html" ]; then
  echo "==> Building frontend (this runs only on first launch)…"
  (cd frontend && { [ -d node_modules ] || npm install; } && npm run build)
fi

echo "==> TelAnalysis is starting on http://127.0.0.1:${PORT}"
# Open the browser once the server is up (best-effort, non-fatal).
( sleep 2; (command -v open >/dev/null && open "http://127.0.0.1:${PORT}") || \
            (command -v xdg-open >/dev/null && xdg-open "http://127.0.0.1:${PORT}") || true ) &

exec "$PY" -m uvicorn api.main:app --host 127.0.0.1 --port "$PORT"
