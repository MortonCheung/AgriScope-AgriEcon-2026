#!/usr/bin/env bash
# AgriScope v1.0 · 本地开发：启动唯一正式后端（另开终端跑前端）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGRISCOPE_API_HOST:-127.0.0.1}"
PORT="${AGRISCOPE_API_PORT:-8787}"
export PROJECT_ROOT="$ROOT"

echo "AgriScope backend  →  http://$HOST:$PORT  (docs: /docs)"
echo "前端另开终端：cd frontend && npm run dev"
exec python3 -m uvicorn app.main:app \
  --app-dir "$ROOT/backend" \
  --host "$HOST" --port "$PORT" --workers 1