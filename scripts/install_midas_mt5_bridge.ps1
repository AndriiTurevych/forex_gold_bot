[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$TerminalPath,
    [ValidateRange(15, 3600)]
    [int]$IntervalSeconds = 60,
    [string]$IngestUrl,
    [string]$TaskName = "MIDAS MT5 Bridge"
)

$ErrorActionPreference = "Stop"
$DefaultIngestUrl = "https://jqmzpwkdbcuqnykhfmvc.supabase.co/functions/v1/ingest-mt5"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Path $PSScriptRoot -Parent
}
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw "REPO_ROOT_NOT_RESOLVED" }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$Runner = Join-Path $RepoRoot "scripts\run_midas_mt5_bridge.ps1"
$HealthPath = Join-Path $RepoRoot "mt5_artifacts\health.json"

if (-not $TerminalPath) {
    $process = Get-Process terminal64 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($process -and $process.Path) { $TerminalPath = $process.Path }
}
if (-not $TerminalPath) {
    $candidate = Join-Path $env:APPDATA "MetaTrader 5\terminal64.exe"
    if (Test-Path $candidate) { $TerminalPath = $candidate }
}
if (-not $TerminalPath -or -not (Test-Path $TerminalPath)) {
    throw "OPEN_MT5_OR_PASS_TERMINAL_PATH"
}
if (-not (Test-Path $Runner)) { throw "BRIDGE_RUNNER_NOT_FOUND:$Runner" }

$processToken = $env:MIDAS_INGEST_TOKEN
$userToken = [Environment]::GetEnvironmentVariable("MIDAS_INGEST_TOKEN", "User")
if (-not $userToken -and $processToken) {
    [Environment]::SetEnvironmentVariable("MIDAS_INGEST_TOKEN", $processToken, "User")
    $userToken = $processToken
}
if (-not $userToken) { throw "MIDAS_INGEST_TOKEN_NOT_SET" }

$processUrl = $env:MIDAS_INGEST_URL
$userUrl = [Environment]::GetEnvironmentVariable("MIDAS_INGEST_URL", "User")
if ([string]::IsNullOrWhiteSpace($IngestUrl)) {
    if (-not [string]::IsNullOrWhiteSpace($processUrl)) {
        $IngestUrl = $processUrl
    }
    elseif (-not [string]::IsNullOrWhiteSpace($userUrl)) {
        $IngestUrl = $userUrl
    }
    else {
        $IngestUrl = $DefaultIngestUrl
    }
}
$IngestUrl = $IngestUrl.Trim()
$uri = $null
if (-not [Uri]::TryCreate($IngestUrl, [UriKind]::Absolute, [ref]$uri)) {
    throw "MIDAS_INGEST_URL_INVALID:$IngestUrl"
}
if ($uri.Scheme -ne "https") { throw "MIDAS_INGEST_URL_MUST_USE_HTTPS" }
[Environment]::SetEnvironmentVariable("MIDAS_INGEST_URL", $IngestUrl, "User")
$env:MIDAS_INGEST_URL = $IngestUrl

# Fail fast before installing: MT5, the feed, analysis, token and MIDAS must all work.
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
& $PowerShell `
    -NoProfile -ExecutionPolicy Bypass -File $Runner `
    -RepoRoot $RepoRoot -TerminalPath $TerminalPath -IntervalSeconds $IntervalSeconds -IngestUrl $IngestUrl -Once
if ($LASTEXITCODE -ne 0) {
    $detail = if (Test-Path $HealthPath) { Get-Content $HealthPath -Raw } else { "NO_HEALTH_FILE" }
    throw "BRIDGE_PREFLIGHT_FAILED:$detail"
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$actionArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`" -RepoRoot `"$RepoRoot`" -TerminalPath `"$TerminalPath`" -IntervalSeconds $IntervalSeconds -IngestUrl `"$IngestUrl`""
$action = New-ScheduledTaskAction -Execute $PowerShell -Argument $actionArguments -WorkingDirectory $RepoRoot
$userId = "$env:USERDOMAIN\$env:USERNAME"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
$preflightAttempt = (Get-Content $HealthPath -Raw | ConvertFrom-Json).attempted_at_utc
Start-ScheduledTask -TaskName $TaskName

$deadline = [DateTime]::UtcNow.AddSeconds(75)
$verified = $false
do {
    Start-Sleep -Seconds 1
    $task = Get-ScheduledTask -TaskName $TaskName
    if (Test-Path $HealthPath) {
        try {
            $health = Get-Content $HealthPath -Raw | ConvertFrom-Json
            $verified = ($health.attempted_at_utc -ne $preflightAttempt) -and [bool]$health.ok
        }
        catch { $verified = $false }
    }
} while (-not $verified -and [DateTime]::UtcNow -lt $deadline)

if (-not $verified) {
    $detail = if (Test-Path $HealthPath) { Get-Content $HealthPath -Raw } else { "NO_HEALTH_FILE" }
    throw "SCHEDULED_BRIDGE_DID_NOT_VERIFY:STATE=$($task.State):$detail"
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
[ordered]@{
    installed = $true
    task = $TaskName
    task_state = [string]$task.State
    last_task_result = $info.LastTaskResult
    terminal_path = $TerminalPath
    interval_seconds = $IntervalSeconds
    ingest_url = $health.ingest_url
    last_success_utc = $health.last_success_utc
    quote_time = $health.quote_time
    signal_stored = [bool]$health.signal_stored
    real_orders_allowed = $false
} | ConvertTo-Json -Compress
