[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$BuildRoot = Join-Path $ProjectRoot 'work\pyinstaller'
$DistRoot = Join-Path $ProjectRoot 'outputs'
$Executable = Join-Path $DistRoot 'Bannerlord Model Forge.exe'
$SpecFile = Join-Path $PSScriptRoot 'BannerlordModelForge.spec'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & (Join-Path $PSScriptRoot 'Setup.ps1')
}

Write-Host 'Installing the local packaging tool...'
& $VenvPython -m pip install -e "$ProjectRoot[build]"
if ($LASTEXITCODE -ne 0) { throw 'Could not install the packaging tool.' }

if (Test-Path -LiteralPath $BuildRoot) {
    $ResolvedBuild = (Resolve-Path -LiteralPath $BuildRoot).Path
    $ExpectedPrefix = (Resolve-Path -LiteralPath (Join-Path $ProjectRoot 'work')).Path
    if (-not $ResolvedBuild.StartsWith($ExpectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean unexpected build path: $ResolvedBuild"
    }
    Remove-Item -LiteralPath $ResolvedBuild -Recurse -Force
}
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
if (Test-Path -LiteralPath $Executable) {
    Remove-Item -LiteralPath $Executable -Force
}

Write-Host 'Building the portable Windows executable...'
$OriginalPath = $env:Path
# Some development hosts put a private Poppler ICU build on PATH. Qt expects the
# Windows ICU shim; letting PyInstaller pick Poppler's same-named DLL breaks QtCore.
$env:Path = (($OriginalPath -split ';') | Where-Object { $_ -and $_ -notmatch '\\poppler\\Library\\bin$' }) -join ';'
try {
    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $DistRoot `
        --workpath (Join-Path $BuildRoot 'build') `
        $SpecFile
    $BuildExitCode = $LASTEXITCODE
}
finally {
    $env:Path = $OriginalPath
}
if ($BuildExitCode -ne 0) { throw 'Executable build failed.' }

Write-Host ''
Write-Host "Built: $Executable" -ForegroundColor Green
Write-Host 'Double-click it to launch Bannerlord Model Forge.'
