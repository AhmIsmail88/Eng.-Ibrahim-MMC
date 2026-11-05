<#
.SYNOPSIS
    Runs the same checks as CI (.github/workflows/ci.yml) on this machine.
.EXAMPLE
    .\scripts\check.ps1            # ruff + mypy + full test suite
    .\scripts\check.ps1 -Quick     # ruff + mypy + unit tests only
#>
param([switch]$Quick)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Missing .venv - create it and install requirements.lock + requirements-dev.lock first." }
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYTHONIOENCODING = "utf-8"

function Step($name, [scriptblock]$body) {
    Write-Host "==> $name" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $name" -ForegroundColor Red; exit $LASTEXITCODE }
}

Step "ruff" { & $python -m ruff check src tests scripts }
Step "mypy" { & $python -m mypy }
if ($Quick) {
    Step "pytest (unit)" { & $python -m pytest -q -p no:cacheprovider tests/unit }
} else {
    Step "pytest" { & $python -m pytest -q -p no:cacheprovider }
}
Write-Host "All checks passed." -ForegroundColor Green
