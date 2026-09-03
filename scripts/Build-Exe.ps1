[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$BuildRoot = Join-Path $ProjectRoot 'work\pyinstaller'
$DistRoot = Join-Path $ProjectRoot 'outputs'
$Executable = Join-Path $DistRoot 'Bannerlord Model Forge.exe'
$EntryPoint = Join-Path $ProjectRoot 'src\bannerlord_model_forge\exe_entry.py'
$BlenderBridge = Join-Path $ProjectRoot 'src\bannerlord_model_forge\blender_bridge.py'
$SkeletonPreview = Join-Path $ProjectRoot 'src\bannerlord_model_forge\blender_skeleton_preview.py'
$SkeletonData = Join-Path $ProjectRoot 'src\bannerlord_model_forge\blender_skeleton_data.py'
$QtRuntimeRoot = Join-Path $ProjectRoot '.venv\Lib\site-packages\PySide6'

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
        --onefile `
        --windowed `
        --noupx `
        --name 'Bannerlord Model Forge' `
        --paths (Join-Path $ProjectRoot 'src') `
        --hidden-import fast_simplification `
        --hidden-import networkx `
        --exclude-module pytest `
        --exclude-module _pytest `
        --exclude-module pytest_cov `
        --exclude-module coverage `
        --exclude-module pygments `
        --exclude-module tkinterdnd2 `
        --add-binary "$(Join-Path $QtRuntimeRoot 'VCRUNTIME140.dll');." `
        --add-binary "$(Join-Path $QtRuntimeRoot 'VCRUNTIME140_1.dll');." `
        --add-binary "$(Join-Path $QtRuntimeRoot 'MSVCP140.dll');." `
        --add-binary "$(Join-Path $QtRuntimeRoot 'MSVCP140_1.dll');." `
        --add-binary "$(Join-Path $QtRuntimeRoot 'MSVCP140_2.dll');." `
        --add-data "$BlenderBridge;bannerlord_model_forge" `
        --add-data "$SkeletonPreview;bannerlord_model_forge" `
        --add-data "$SkeletonData;bannerlord_model_forge" `
        --distpath $DistRoot `
        --workpath (Join-Path $BuildRoot 'build') `
        --specpath $BuildRoot `
        $EntryPoint
    $BuildExitCode = $LASTEXITCODE
}
finally {
    $env:Path = $OriginalPath
}
if ($BuildExitCode -ne 0) { throw 'Executable build failed.' }

Write-Host ''
Write-Host "Built: $Executable" -ForegroundColor Green
Write-Host 'Double-click it to launch Bannerlord Model Forge.'
