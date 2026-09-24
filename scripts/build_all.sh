#!/usr/bin/env sh
# Build everything after setup: datasets -> SQLite -> int8 models -> vector index (demo subset) -> Dorar cache.
# Safe to re-run: every step skips work that is already done.
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
export PYTHONIOENCODING=utf-8
$PY scripts/download_data.py
$PY scripts/build_db.py
$PY scripts/fetch_models.py
$PY scripts/build_index.py
# Dorar cache: uses the network once; the app works offline from the cache afterwards.
$PY scripts/seed_dorar.py || echo "Dorar seeding skipped (network) - the app still works, degraded"
echo "Build done. Next: ./scripts/run.sh  then open http://127.0.0.1:8000"
