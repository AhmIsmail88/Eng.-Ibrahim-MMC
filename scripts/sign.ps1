# ENG. IBRAHIM — optional Authenticode signing (SPEC 26.6)
#
# Signs the given files only when a certificate is configured; otherwise it prints a note
# and returns, so unsigned builds keep working. Configure through environment variables
# (never commit a certificate or its password):
#   ENG_IBRAHIM_SIGN_CERT      path to the .pfx code-signing certificate
#   ENG_IBRAHIM_SIGN_PASSWORD  its password
#   ENG_IBRAHIM_SIGN_TIMESTAMP timestamp server (default: http://timestamp.digicert.com)
param([Parameter(Mandatory = $true)][string[]]$Files)
$ErrorActionPreference = "Stop"

$cert = $env:ENG_IBRAHIM_SIGN_CERT
if (-not $cert) {
    Write-Host "Signing skipped: ENG_IBRAHIM_SIGN_CERT is not set (SmartScreen will warn)."
    return
}
if (-not (Test-Path $cert)) { throw "Certificate not found: $cert" }

$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe `
    -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match "\\x64\\" } |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signtool) { throw "signtool.exe not found: install the Windows SDK signing tools." }

$timestamp = if ($env:ENG_IBRAHIM_SIGN_TIMESTAMP) { $env:ENG_IBRAHIM_SIGN_TIMESTAMP } `
             else { "http://timestamp.digicert.com" }
foreach ($file in $Files) {
    & $signtool.FullName sign /fd SHA256 /f $cert /p $env:ENG_IBRAHIM_SIGN_PASSWORD `
        /tr $timestamp /td SHA256 /d "ENG. IBRAHIM" $file
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $file" }
    Write-Host "Signed: $file"
}
