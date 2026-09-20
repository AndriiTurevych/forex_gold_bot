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
    ai_gate_status = $health.ai_gate_status
    ai_decision = $health.ai_decision
    ai_reason_code = $health.ai_reason_code
    ea_command_published = [bool]$health.ea_command_published
    ea_command_action = $health.ea_command_action
    risk_approved = [bool]$health.risk_approved
    demo_execution_allowed = [bool]$health.demo_execution_allowed
    final_action = $health.final_action
    demo_execution_status = $health.demo_execution_status
    demo_execution_reason = $health.demo_execution_reason
    demo_order_sent = [bool]$health.demo_order_sent
    position_managed = [bool]$health.position_managed
    error = $health.error
    real_orders_allowed = $false
} | ConvertTo-Json -Compress
if (-not $ok) { exit 1 }
