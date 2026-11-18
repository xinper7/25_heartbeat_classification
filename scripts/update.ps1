param([switch]$SkipAgentDownload)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
& git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw 'Git update failed. Resolve local changes or network access and retry.' }
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop.ps1
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the previous services.' }
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed.' }
$argsForStart = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/start.ps1', '-Build')
if ($SkipAgentDownload) { $argsForStart += '-SkipAgentDownload' }
& powershell @argsForStart
if ($LASTEXITCODE -ne 0) { throw 'Updated services failed to start.' }
