[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'Windows Package Manager (winget) was not found. Install Blender from https://www.blender.org/download/ instead.'
}

Write-Host 'Blender is optional and is installed from Blender Foundation through winget.'
Write-Host 'It enables FBX conversion and the future final skeletal-export stage.'
winget install --exact --id BlenderFoundation.Blender --accept-package-agreements --accept-source-agreements
