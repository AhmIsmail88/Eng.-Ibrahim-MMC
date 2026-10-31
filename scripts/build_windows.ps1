# ENG. IBRAHIM — Windows build (SPEC 26.3)
# Usage:  .\scripts\build_windows.ps1 [-Mode standalone|onefile] [-SkipTests]
param(
    [ValidateSet("standalone", "onefile")]
    [string]$Mode = "standalone",
    [switch]$SkipTests
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.13 -m venv .venv
}
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.lock

if (-not $SkipTests) {
    & $python -m pip install -r requirements-dev.lock
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed — build aborted." }
}

# Deployment config lives in pyproject.toml ([tool.pyside6.deploy]); the icon,
# assets/ and migrations are data files and must be bundled explicitly.
& $python -m pyside6-deploy main.py --mode $Mode
if ($LASTEXITCODE -ne 0) { throw "pyside6-deploy failed." }

$exe = Get-ChildItem -Path dist -Recurse -Filter "ENG_IBRAHIM.exe" | Select-Object -First 1
if (-not $exe) { throw "ENG_IBRAHIM.exe not found in dist\." }
Copy-Item -Recurse -Force "assets", "migrations", "SPEC.md" (Split-Path $exe.FullName)
Write-Host "Build OK: $($exe.FullName)"
Write-Host "Next: .\scripts\package_installer.ps1"
