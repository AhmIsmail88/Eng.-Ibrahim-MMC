# Compile the Inno Setup installer (SPEC 26.6)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 (ISCC.exe) not found. Install it, or ship the standalone folder as-is."
}
Push-Location $root
try {
    & $iscc "installer\installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "ISCC failed." }
} finally {
    Pop-Location
}
Write-Host "Installer written to dist\installer\"
