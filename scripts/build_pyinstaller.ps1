# ENG. IBRAHIM — PyInstaller build (fallback when pyside6-deploy/Nuitka is unavailable)
param([switch]$OneFile)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
python -m pip install pyinstaller --quiet
$mode = if ($OneFile) { "--onefile" } else { "--onedir" }
python -m PyInstaller --noconfirm --clean --windowed $mode --name ENG_IBRAHIM `
    --paths src `
    --icon assets/icons/ENG_IBRAHIM_Icon.ico `
    --add-data "assets;assets" --add-data "migrations;migrations" --add-data "SPEC.md;." `
    --add-data "src/eng_ibrahim/localization;eng_ibrahim/localization" `
    main.py
Write-Host "Output: dist\ENG_IBRAHIM\ENG_IBRAHIM.exe"
