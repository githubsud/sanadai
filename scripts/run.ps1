$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 @args
