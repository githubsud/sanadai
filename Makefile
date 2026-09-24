# Unix/macOS convenience targets. Windows: use scripts/*.ps1 (same steps).
PY ?= .venv/bin/python

.PHONY: setup data db index seed run test lint eval all

setup:
	python3 -m venv .venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install -r requirements.txt
	[ -f .env ] || cp .env.example .env

data:
	$(PY) scripts/download_data.py

db:
	$(PY) scripts/build_db.py

index:
	$(PY) scripts/build_index.py

seed:
	$(PY) scripts/seed_dorar.py

run:
	$(PY) -m uvicorn app.main:app --reload --port 8000

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

eval:
	$(PY) scripts/run_eval.py

all: data db index seed
