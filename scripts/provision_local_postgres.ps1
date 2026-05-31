# Local Postgres for sandbox dev (Docker). Does not provision Azure.
# Usage: .\scripts\provision_local_postgres.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Set-Location $RepoRoot

Write-Host "Starting Docker Postgres (postgres:16 on localhost:5432) ..."
docker compose up -d postgres

Write-Host "Waiting for Postgres to accept connections ..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T postgres pg_isready -U boardroom_app -d boardroom 2>$null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Write-Error "Postgres did not become ready in time."
}

$env:DATABASE_URL = "postgresql://boardroom_app:local_dev_password@localhost:5432/boardroom"
Write-Host "DATABASE_URL=$env:DATABASE_URL"

if (Test-Path ".\.venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
} else {
    $python = "python"
}

& $python scripts/run_migrations.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Local Postgres is ready."
Write-Host "Add to your .env (repo root) for FastAPI / pipeline:"
Write-Host "  DATABASE_URL=postgresql://boardroom_app:local_dev_password@localhost:5432/boardroom"
Write-Host "  SANDBOX_USER_SLUG=local-sandbox"
Write-Host ""
Write-Host "Restart uvicorn after setting DATABASE_URL, then re-import sandbox CSV."
