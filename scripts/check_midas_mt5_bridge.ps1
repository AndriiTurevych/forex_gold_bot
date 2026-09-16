[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$TaskName = "MIDAS MT5 Bridge",
    [ValidateRange(60, 3600)]
    [int]$MaxAgeSeconds = 180
)

$ErrorActionPreference = "Stop"
$HealthPath = Join-Path ([IO.Path]::GetFullPath($RepoRoot)) "mt5_artifacts\health.json"
if (-not (Test-Path $HealthPath)) { throw "HEALTH_FILE_NOT_FOUND:$HealthPath" }

$health = Get-Content $HealthPath -Raw | ConvertFrom-Json
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
$lastSuccess = [DateTime]::Parse($health.last_success_utc).ToUniversalTime()
$age = ([DateTime]::UtcNow - $lastSuccess).TotalSeconds
$fresh = $age -le $MaxAgeSeconds
$taskHealthy = ([string]$task.State -eq "Running") -or ([string]$task.State -eq "Ready")
$ok = [bool]$health.ok -and $fresh -and $taskHealthy

[ordered]@{
    ok = $ok
    task_state = [string]$task.State
    last_task_result = $info.LastTaskResult
    last_success_utc = $health.last_success_utc
    age_seconds = [Math]::Round($age, 1)
    quote_time = $health.quote_time
    signal_stored = [bool]$health.signal_stored
    error = $health.error
    real_orders_allowed = $false
} | ConvertTo-Json -Compress
if (-not $ok) { exit 1 }
