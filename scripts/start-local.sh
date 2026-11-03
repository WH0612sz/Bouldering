#!/bin/sh
set -eu
CLIMB_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$CLIMB_ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  echo "缺少Python环境，请按README安装backend依赖。" >&2
  exit 1
fi
POSE_ROOT="$(dirname "$CLIMB_ROOT")/技术验证"
export POSE_MODEL=${POSE_MODEL:-"$POSE_ROOT/models/pose_landmarker_full.task"}
export POSE_PYTHON=${POSE_PYTHON:-"$POSE_ROOT/.venv/bin/python"}
export APP_ENV=development
export ALLOW_DEV_LOGIN=1
export PUBLIC_URL=${PUBLIC_URL:-http://127.0.0.1:8000}
.venv/bin/python -m app.init_db
.venv/bin/python -m app.worker &
CLIMB_WORKER_PID=$!
trap 'kill "$CLIMB_WORKER_PID" 2>/dev/null || true' EXIT INT TERM
printf '本地联调入口：http://127.0.0.1:8000/dev/\n'
.venv/bin/python -m uvicorn app.main:create_app --factory --host "${BIND_HOST:-127.0.0.1}" --port 8000 --no-access-log
