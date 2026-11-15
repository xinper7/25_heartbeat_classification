param(
    [switch]$StopDatabase,
    [ValidateSet('api','worker','frontend')]
    [string[]]$Service = @('api','worker','frontend')
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pidFile = Join-Path $projectRoot 'runtime\processes.json'
if (Test-Path -LiteralPath $pidFile) {
    # Windows PowerShell 5.1 returns a JSON array as one pipeline object;
    # wrapping that pipeline in @() would produce a nested array.
    $records = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $remaining = @()
    $changed = $false
    foreach ($entry in $records) {
        if ($entry.name -notin $Service) {
            $remaining += $entry
            continue
        }
        $changed = $true
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.pid)" -ErrorAction SilentlyContinue
        $expectedScript = switch ($entry.name) {
            'api' { 'run_api.py' }
            'worker' { 'run_worker.py' }
            'frontend' { 'vite.js' }
        }
        if ($proc -and $proc.CommandLine -and $proc.CommandLine.Contains($projectRoot) -and $proc.CommandLine.Contains($expectedScript)) {
            # Windows venv python.exe is a redirector. Its child owns the socket;
            # terminating only the recorded parent can leave the port occupied.
            & taskkill.exe /PID ([string]$entry.pid) /T /F | Out-Host
            if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $entry.pid -ErrorAction SilentlyContinue)) {
                throw ('Could not stop the project '+$entry.name+' process tree.')
            }
            Write-Host ('Stopped project '+$entry.name+' process tree.')
        } elseif ($proc) {
            throw ('Recorded PID no longer belongs to the expected project service; refusing to stop it: '+$entry.name)
        }
    }
    if ($changed) {
        if ($remaining.Count -gt 0) {
            ConvertTo-Json -InputObject @($remaining) | Set-Content -LiteralPath $pidFile -Encoding UTF8
        } else {
            Remove-Item -LiteralPath $pidFile
        }
    }
}
if ($StopDatabase) {
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $projectRoot 'scripts\project_mysql.py') stop
}
