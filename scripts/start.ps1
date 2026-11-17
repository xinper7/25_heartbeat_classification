param([switch]$Dev, [switch]$Build, [switch]$SkipAgentDownload)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path -LiteralPath '.env')) { throw 'Run scripts/setup.ps1 to create the local .env file.' }
if (Test-Path -LiteralPath 'runtime\processes.json') {
    $oldRecords = Get-Content -LiteralPath 'runtime\processes.json' -Raw | ConvertFrom-Json
    foreach ($entry in $oldRecords) {
        if (Get-Process -Id $entry.pid -ErrorAction SilentlyContinue) { throw 'A recorded service is still running. Use scripts/stop.ps1 before starting again.' }
    }
}
$ports = @(8000)
if ($Dev) { $ports += 5173 }
foreach ($port in $ports) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try {
        $listener.Start()
    } catch [System.Net.Sockets.SocketException] {
        throw "Port $port is unavailable. Stop the previous project or debug session, or release the port before starting."
    } finally {
        $listener.Stop()
    }
}
New-Item -ItemType Directory -Path 'runtime' -Force | Out-Null
if (-not $SkipAgentDownload) {
    & $projectPython scripts\ensure_agent.py
    if ($LASTEXITCODE -ne 0) { throw 'Agent installation failed. Check network/model directory, or use -SkipAgentDownload for classifier-only mode.' }
}

$localEnv = Get-Content -LiteralPath '.env' -Raw
if ($localEnv -match '(?m)^DATABASE_URL=[^\r\n]*@127\.0\.0\.1:3307/' -and (Test-Path -LiteralPath 'runtime\mysql-process.json')) {
    $dbProcess = Get-Content -LiteralPath 'runtime\mysql-process.json' -Raw | ConvertFrom-Json
    if ($dbProcess.binary) {
        & $projectPython scripts\project_mysql.py start --mysqld $dbProcess.binary
        if ($LASTEXITCODE -ne 0) { throw 'Project MySQL could not start.' }
    }
}
if ($Build -or (-not $Dev -and -not (Test-Path -LiteralPath 'frontend\dist\index.html'))) {
    Push-Location frontend
    try { & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } } finally { Pop-Location }
}
& $projectPython scripts\init_db.py
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed. Check .env and MySQL.' }
$records = @()
foreach ($entry in @(@{name='api';script='run_api.py'},@{name='worker';script='run_worker.py'})) {
    $script = Join-Path $projectRoot ('scripts\' + $entry.script)
    $proc = Start-Process -FilePath $projectPython -ArgumentList @('"' + $script + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot ('runtime\'+$entry.name+'.out.log')) -RedirectStandardError (Join-Path $projectRoot ('runtime\'+$entry.name+'.err.log')) -PassThru
    $records += @{name=$entry.name;pid=$proc.Id}
}
if ($Dev) {
    $viteScript = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
    $nodePath = (Get-Command node.exe).Source
    $proc = Start-Process -FilePath $nodePath -ArgumentList @('"'+$viteScript+'"','--host','127.0.0.1','--port','5173') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'runtime\frontend.out.log') -RedirectStandardError (Join-Path $projectRoot 'runtime\frontend.err.log') -PassThru
    $records += @{name='frontend';pid=$proc.Id}
}
$records | ConvertTo-Json | Set-Content -LiteralPath 'runtime\processes.json' -Encoding UTF8
$url = if ($Dev) { 'http://127.0.0.1:5173' } else { 'http://127.0.0.1:8000' }
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    foreach ($entry in $records) {
        if (-not (Get-Process -Id $entry.pid -ErrorAction SilentlyContinue)) {
            throw "The $($entry.name) process stopped. See runtime/$($entry.name).err.log. Use scripts/stop.ps1 before restarting."
        }
    }
    try {
        $response = Invoke-RestMethod "$url/api/v1/health" -TimeoutSec 2
        if ($response.result.ready) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'Service did not become ready. See runtime/api.err.log. Use scripts/stop.ps1 before restarting.' }
Write-Host "Application ready: $url"
Write-Host 'API docs: http://127.0.0.1:8000/docs'
Write-Host 'Login credentials: BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD in local .env.'
