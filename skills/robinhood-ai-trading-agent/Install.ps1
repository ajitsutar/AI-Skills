param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
& python (Join-Path $PSScriptRoot 'scripts\install_skill.py') --destination $Destination
exit $LASTEXITCODE
