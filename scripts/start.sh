#!/usr/bin/env bash

set -euo pipefail

export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
export WEB_CONCURRENCY=1

if [[ -d /var/data && "${DATABASE_URL:-sqlite}" == sqlite* ]]; then
    export DATABASE_URL="sqlite+aiosqlite:////var/data/localhub.db"
fi

python -m scripts.migrate_db
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --limit-concurrency "${UVICORN_LIMIT_CONCURRENCY:-8}" --backlog "${UVICORN_BACKLOG:-32}" --timeout-keep-alive "${UVICORN_KEEP_ALIVE:-5}"
