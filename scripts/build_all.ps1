# Build everything after setup: datasets -> SQLite -> int8 models -> vector index (demo subset) -> Dorar cache.
# Safe to re-run: every step skips work that is already done.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = ".\.venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
& $py scripts\download_data.py;  if ($LASTEXITCODE) { exit 1 }
& $py scripts\build_db.py;       if ($LASTEXITCODE) { exit 1 }
& $py scripts\fetch_models.py;   if ($LASTEXITCODE) { exit 1 }
& $py scripts\build_index.py;    if ($LASTEXITCODE) { exit 1 }
# Dorar cache: uses the network once; the app works offline from the cache afterwards.
& $py scripts\seed_dorar.py
Write-Host "Build done. Next: .\scripts\run.ps1  then open http://127.0.0.1:8000"
