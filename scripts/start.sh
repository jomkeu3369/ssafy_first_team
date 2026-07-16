#!/usr/bin/env bash

set -euo pipefail

if [[ -d /var/data && "${DATABASE_URL:-sqlite}" == sqlite* ]]; then
    export DATABASE_URL="sqlite+aiosqlite:////var/data/localhub.db"
fi

python -m scripts.migrate_db
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
