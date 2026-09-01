[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

Write-Host 'Bannerlord Model Forge setup'
Write-Host "Project: $ProjectRoot"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host 'Creating an isolated Python environment...'
    python -m venv (Join-Path $ProjectRoot '.venv')
}

Write-Host 'Installing application and test dependencies...'
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e "$ProjectRoot[dev]"

Write-Host ''
Write-Host 'Setup complete. Run scripts\Start.ps1 to open the app.' -ForegroundColor Green
