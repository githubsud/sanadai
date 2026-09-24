#!/usr/bin/env sh
# Unix setup: creates .venv, installs deps, copies .env.example -> .env
set -e
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "Setup done. Next: ./scripts/build_all.sh then ./scripts/run.sh"
