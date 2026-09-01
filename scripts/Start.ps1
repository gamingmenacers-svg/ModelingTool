[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & (Join-Path $PSScriptRoot 'Setup.ps1')
}

Set-Location -LiteralPath $ProjectRoot
& $VenvPython -m bannerlord_model_forge
