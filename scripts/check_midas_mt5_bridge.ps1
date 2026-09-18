[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$TaskName = "MIDAS MT5 Bridge",
    [ValidateRange(60, 3600)]
    [int]$MaxAgeSeconds = 180
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Path $PSScriptRoot -Parent
}
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw "REPO_ROOT_NOT_RESOLVED" }
$HealthPath = Join-Path ([IO.Path]::GetFullPath($RepoRoot)) "mt5_artifacts\health.json"
if (-not (Test-Path $HealthPath)) { throw "HEALTH_FILE_NOT_FOUND:$HealthPath" }

$health = Get-Content $HealthPath -Raw | ConvertFrom-Json
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName

$lastSuccess = $null
$age = [double]::PositiveInfinity
$fresh = $false
if (-not [string]::IsNullOrWhiteSpace([string]$health.last_success_utc)) {
    try {
        $lastSuccess = [DateTime]::Parse([string]$health.last_success_utc).ToUniversalTime()
        $age = ([DateTime]::UtcNow - $lastSuccess).TotalSeconds
        $fresh = $age -le $MaxAgeSeconds
    }
    catch {
        $fresh = $false
    }
}

$taskHealthy = ([string]$task.State -eq "Running") -or ([string]$task.State -eq "Ready")
$ok = [bool]$health.ok -and $fresh -and $taskHealthy

[ordered]@{
    ok = $ok
    task_state = [string]$task.State
    last_task_result = $info.LastTaskResult
    pid = $health.pid
    loop_started_at_utc = $health.loop_started_at_utc
    attempted_at_utc = $health.attempted_at_utc
    last_success_utc = $health.last_success_utc
    age_seconds = if ([double]::IsPositiveInfinity($age)) { $null } else { [Math]::Round($age, 1) }
    quote_time = $health.quote_time
    signal_stored = [bool]$health.signal_stored
    ingest_url = $health.ingest_url
    error = $health.error
    real_orders_allowed = $false
} | ConvertTo-Json -Compress
if (-not $ok) { exit 1 }
