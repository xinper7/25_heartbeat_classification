param([ValidateSet('api','worker','both')][string]$Target='api')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot

# Only services registered by this project's background launcher are stopped.
# Unrelated applications and active VS Code debug sessions are not terminated.
if ($Target -eq 'both') {
    & (Join-Path $PSScriptRoot 'stop.ps1') -Service @('api','worker')
} else {
    & (Join-Path $PSScriptRoot 'stop.ps1') -Service @($Target)
}

if ($Target -in @('api','both')) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'),8000)
    try {
        $listener.Start()
    } catch {
        $owners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
        throw ('Port 8000 is still in use (PID: '+($owners -join ', ')+'). Stop the previous VS Code debugging session with Shift+F5 before starting again. No unrelated process was stopped.')
    } finally {
        $listener.Stop()
    }
}

$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Run scripts/setup.ps1 first.' }
$localEnv = Get-Content -LiteralPath '.env' -Raw
if ($localEnv -match '(?m)^DATABASE_URL=[^\r\n]*@127\.0\.0\.1:3307/' -and (Test-Path -LiteralPath 'runtime\mysql-process.json')) {
    $dbProcess = Get-Content -LiteralPath 'runtime\mysql-process.json' -Raw | ConvertFrom-Json
    if ($dbProcess.binary) {
        & $projectPython scripts\project_mysql.py start --mysqld $dbProcess.binary
        if ($LASTEXITCODE -ne 0) { throw 'Project database could not start.' }
    }
}
& $projectPython scripts\init_db.py
if ($LASTEXITCODE -ne 0) { throw 'Database is not ready; check .env and MySQL.' }
Write-Host ('Debug preparation complete: '+$Target)
