# Launch the Kokoro Studio backend (works from any machine/checkout path).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "backend")

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "No venv found - run setup.bat first." -ForegroundColor Red
    exit 1
}

& ".\venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
