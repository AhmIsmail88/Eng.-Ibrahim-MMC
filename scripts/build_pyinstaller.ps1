# ENG. IBRAHIM — PyInstaller build (fallback when pyside6-deploy/Nuitka is unavailable)
param([switch]$OneFile)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
# Build with the project's virtual environment: the system Python may lack runtime
# packages (qrcode, Pillow, argon2...) and PyInstaller only bundles what it can import.
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -m pip install -r requirements.lock pyinstaller --quiet
$mode = if ($OneFile) { "--onefile" } else { "--onedir" }
& $py -m PyInstaller --noconfirm --clean --windowed $mode --name ENG_IBRAHIM `
    --paths src `
    --icon assets/icons/ENG_IBRAHIM_Icon.ico `
    --add-data "assets;assets" --add-data "migrations;migrations" --add-data "SPEC.md;." `
    --add-data "src/eng_ibrahim/localization;eng_ibrahim/localization" `
    main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
$exe = if ($OneFile) { "dist\ENG_IBRAHIM.exe" } else { "dist\ENG_IBRAHIM\ENG_IBRAHIM.exe" }
& "$PSScriptRoot\sign.ps1" -Files $exe
Write-Host "Output: $exe"
