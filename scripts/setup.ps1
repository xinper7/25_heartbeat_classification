param([switch]$DevDependencies)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'Install Node.js 24 and reopen PowerShell before running setup.'
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.13 with the Windows py launcher before running setup.'
    }
    & py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 virtual environment creation failed.' }
}
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$requirements = if ($DevDependencies) { 'backend\requirements-dev.lock.txt' } else { 'backend\requirements.lock.txt' }
& $projectPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies installation failed.' }
& $projectPython -m pip install -r backend\requirements-agent.txt
if ($LASTEXITCODE -ne 0) { throw 'Agent dependencies installation failed.' }
& $projectPython scripts\local_secrets.py
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the local .env file.' }
Push-Location frontend
try {
    & npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependencies installation failed.' }
} finally { Pop-Location }
Write-Host 'Dependencies ready. Configure MySQL as described in README.md, then run scripts/start.ps1.'
Write-Host 'Initial administrator password is in the local .env file; do not commit it.'
