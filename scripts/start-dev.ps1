# scripts/start-dev.ps1
# Launches zest-web, zest-app-server, and zest-service in background.
# Startup order: 1) frontend (5173) → 2) app-server (9000) → 3) service (8001)
# Usage:
#   ./scripts/start-dev.ps1            # start all three
#   ./scripts/start-dev.ps1 -Stop      # stop all three
#   ./scripts/start-dev.ps1 -Status    # show running state
# Requires: redis and mysql running (docker compose up -d).

[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Status,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Services = @(
    @{ Name = "web";         Title = "Zest Web      (5173)";  Cmd = { pnpm dev } ; Cwd = Join-Path $Root "zest-web" }
    @{ Name = "app-server";  Title = "Zest AppServer (9000)";  Cmd = { uv run uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload } ; Cwd = Join-Path $Root "zest-app-server" }
    @{ Name = "service";     Title = "Zest Service  (8001)";  Cmd = { uv run python -m server --host 0.0.0.0 --port 8001 --reload } ; Cwd = Join-Path $Root "zest-agent-server\zest-service" }
)

$LogDir = Join-Path $Root ".tmp"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Stop-All {
    Get-Process -Name "python","node","uvicorn" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like "*Zest*" -or $_.Path -like "*zest*" } |
        ForEach-Object {
            Write-Host "Stopping $($_.ProcessName) ($($_.Id))"
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
    Write-Host "All Zest dev processes stopped."
}

function Show-Status {
    foreach ($s in $Services) {
        $pids = (Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe'" -ErrorAction SilentlyContinue) |
            Where-Object { $_.CommandLine -like "*$($s.Name)*" -or $_.CommandLine -like "*zest*" }
        if ($pids) {
            Write-Host "[RUNNING] $($s.Name) -> PID(s): $($pids.ProcessId -join ', ')"
        } else {
            Write-Host "[STOPPED] $($s.Name)"
        }
    }
}

if ($Status) { Show-Status; return }
if ($Stop)   { Stop-All;   return }

# Pre-flight: check redis & mysql
foreach ($port in 6379, 3306) {
    $ok = (Test-NetConnection -ComputerName 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)
    if (-not $ok) {
        Write-Warning "Port $port not reachable. Run: docker compose up -d"
    }
}

foreach ($s in $Services) {
    $log = Join-Path $LogDir "zest-$($s.Name).log"
    Write-Host "Starting $($s.Name) -> log: $log"
    Set-Location $s.Cwd
    if ($Foreground) {
        Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "& { Set-Location '$($s.Cwd)'; $($s.Cmd.ToString()) }" -WindowStyle Normal
    } else {
        $cmdStr = $s.Cmd.ToString().Trim("{ }")
        $job = Start-Job -ScriptBlock ([scriptblock]::Create("Set-Location '$($s.Cwd)'; $cmdStr")) -Name "zest-$($s.Name)"
        Write-Host "  Job ID: $($job.Id)"
    }
}
Set-Location $Root
Write-Host ""
Write-Host "All services started in background jobs (order: web -> app-server -> service)."
Write-Host "Logs:       $LogDir\zest-*.log"
Write-Host "Stop:       ./scripts/start-dev.ps1 -Stop"
Write-Host "Status:     ./scripts/start-dev.ps1 -Status"
Write-Host "Endpoints:  http://127.0.0.1:5173  (web)"
Write-Host "            http://127.0.0.1:9000  (app-server)"
Write-Host "            http://127.0.0.1:8001  (service)"
