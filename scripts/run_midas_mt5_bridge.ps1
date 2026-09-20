[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [Parameter(Mandatory = $true)]
    [string]$TerminalPath,
    [ValidateRange(15, 3600)]
    [int]$IntervalSeconds = 60,
    [string]$IngestUrl,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$SyncScript = Join-Path $RepoRoot "scripts\sync_mt5_to_midas.py"
$ArtifactDir = Join-Path $RepoRoot "mt5_artifacts"
$LogPath = Join-Path $ArtifactDir "bridge.log"
$HealthPath = Join-Path $ArtifactDir "health.json"
$HealthTemp = "$HealthPath.tmp"
$DecisionPath = Join-Path $ArtifactDir "decision.json"
$EACommandArtifactPath = Join-Path $ArtifactDir "ea_command.json"
$ForwardScript = Join-Path $RepoRoot "scripts\collect_midas_forward_results.py"
$ForwardOutput = Join-Path $ArtifactDir "resolved_trades.csv"
$DemoScript = Join-Path $RepoRoot "scripts\run_midas_demo_execution.py"
$DemoOutputPath = Join-Path $ArtifactDir "demo_execution.json"
$DefaultIngestUrl = "https://jqmzpwkdbcuqnykhfmvc.supabase.co/functions/v1/ingest-mt5"

New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null
if (-not (Test-Path $Python)) { throw "PYTHON_NOT_FOUND:$Python" }
if (-not (Test-Path $SyncScript)) { throw "SYNC_SCRIPT_NOT_FOUND:$SyncScript" }
if (-not (Test-Path $TerminalPath)) { throw "MT5_TERMINAL_NOT_FOUND:$TerminalPath" }

$savedToken = [Environment]::GetEnvironmentVariable("MIDAS_INGEST_TOKEN", "User")
if (-not $env:MIDAS_INGEST_TOKEN -and $savedToken) {
    $env:MIDAS_INGEST_TOKEN = $savedToken
}
if (-not $env:MIDAS_INGEST_TOKEN) { throw "MIDAS_INGEST_TOKEN_NOT_SET" }

$savedUrl = [Environment]::GetEnvironmentVariable("MIDAS_INGEST_URL", "User")
if ([string]::IsNullOrWhiteSpace($IngestUrl)) {
    if (-not [string]::IsNullOrWhiteSpace($env:MIDAS_INGEST_URL)) {
        $IngestUrl = $env:MIDAS_INGEST_URL
    }
    elseif (-not [string]::IsNullOrWhiteSpace($savedUrl)) {
        $IngestUrl = $savedUrl
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
$env:MIDAS_INGEST_URL = $IngestUrl
$env:PYTHONPATH = $RepoRoot

$lastSuccessUtc = $null
if (Test-Path $HealthPath) {
    try { $lastSuccessUtc = (Get-Content $HealthPath -Raw | ConvertFrom-Json).last_success_utc } catch {}
}

$loopStartedUtc = [DateTime]::UtcNow.ToString("o")
do {
    $attemptUtc = [DateTime]::UtcNow.ToString("o")
    $health = [ordered]@{
        ok = $false
        task = "MIDAS MT5 Bridge"
        pid = $PID
        loop_started_at_utc = $loopStartedUtc
        attempted_at_utc = $attemptUtc
        last_success_utc = $lastSuccessUtc
        quote_time = $null
        signal_stored = $false
        ingest_url = $IngestUrl
        error = $null
        ai_gate_status = $null
        ai_decision = $null
        ai_reason_code = $null
        ea_command_published = $false
        ea_command_action = "ABSTAIN"
        risk_approved = $false
        demo_execution_allowed = $false
        final_action = "ABSTAIN"
        demo_execution_status = "DISABLED"
        demo_execution_reason = "MIDAS_DEMO_EXECUTION_DISABLED"
        demo_order_sent = $false
        position_managed = $false
        resolved_trades = 0
        real_orders_allowed = $false
    }
    try {
        $arguments = @(
            $SyncScript,
            "--terminal-path", $TerminalPath,
            "--server-utc-offset-hours", "3",
            "--mt5-timeout-ms", "10000",
            "--url", $IngestUrl
        )
        $lines = @(& $Python @arguments 2>&1 | ForEach-Object { "$_" })
        $exitCode = $LASTEXITCODE
        foreach ($line in $lines) { Add-Content -Path $LogPath -Value "[$attemptUtc] $line" -Encoding UTF8 }
        if ($exitCode -ne 0) { throw "SYNC_EXIT_$exitCode" }
        if ($lines.Count -lt 1) { throw "SYNC_NO_OUTPUT" }
        $result = $lines[-1] | ConvertFrom-Json
        if ($result.ok -ne $true) { throw "SYNC_RESULT_NOT_OK" }

        if (Test-Path $DecisionPath) {
            try {
                $decision = Get-Content $DecisionPath -Raw | ConvertFrom-Json
                $health.ai_gate_status = [string]$decision.ai_gate.status
                $health.ai_decision = [string]$decision.ai_gate.decision
                $health.ai_reason_code = [string]$decision.ai_gate.reason_code
                $health.risk_approved = [bool]$decision.risk_gate.approved
                $health.demo_execution_allowed = [bool]$decision.demo_execution_allowed
                $health.final_action = [string]$decision.final_action
            }
            catch {
                throw "DECISION_ARTIFACT_INVALID:$($_.Exception.Message)"
            }
        }
        else {
            throw "DECISION_ARTIFACT_MISSING"
        }

        if (Test-Path $EACommandArtifactPath) {
            try {
                $eaCommand = Get-Content $EACommandArtifactPath -Raw | ConvertFrom-Json
                $health.ea_command_published = [bool]$eaCommand.published
                if (-not [string]::IsNullOrWhiteSpace([string]$eaCommand.action)) {
                    $health.ea_command_action = [string]$eaCommand.action
                }
            }
            catch {
                throw "EA_COMMAND_ARTIFACT_INVALID:$($_.Exception.Message)"
            }
        }

        if (Test-Path $ForwardScript) {
            $forwardLines = @(& $Python $ForwardScript --terminal-path $TerminalPath --output $ForwardOutput 2>&1 | ForEach-Object { "$_" })
            $forwardExit = $LASTEXITCODE
            foreach ($line in $forwardLines) { Add-Content -Path $LogPath -Value "[$attemptUtc] FORWARD $line" -Encoding UTF8 }
            if ($forwardExit -ne 0) { throw "FORWARD_RESULTS_EXIT_$forwardExit" }
            if ($forwardLines.Count -ge 1) {
                $forwardResult = $forwardLines[-1] | ConvertFrom-Json
                $health.resolved_trades = [int]$forwardResult.resolved_trades
            }
        }

        $savedDemoEnabled = [Environment]::GetEnvironmentVariable("MIDAS_DEMO_EXECUTION_ENABLED", "User")
        if (-not $env:MIDAS_DEMO_EXECUTION_ENABLED -and $savedDemoEnabled) {
            $env:MIDAS_DEMO_EXECUTION_ENABLED = $savedDemoEnabled
        }
        $demoEnabled = -not [string]::IsNullOrWhiteSpace($env:MIDAS_DEMO_EXECUTION_ENABLED) -and
            $env:MIDAS_DEMO_EXECUTION_ENABLED.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")
        if ($demoEnabled) {
            if (-not (Test-Path $DemoScript)) { throw "DEMO_EXECUTION_SCRIPT_NOT_FOUND:$DemoScript" }
            $demoLines = @(& $Python $DemoScript --terminal-path $TerminalPath 2>&1 | ForEach-Object { "$_" })
            $demoExit = $LASTEXITCODE
            foreach ($line in $demoLines) { Add-Content -Path $LogPath -Value "[$attemptUtc] DEMO $line" -Encoding UTF8 }
            if ($demoExit -ne 0) { throw "DEMO_EXECUTION_EXIT_$demoExit" }
            if ($demoLines.Count -lt 1) { throw "DEMO_EXECUTION_NO_OUTPUT" }
            $demoResult = $demoLines[-1] | ConvertFrom-Json
            $health.demo_execution_status = [string]$demoResult.execution.status
            $health.demo_execution_reason = [string]$demoResult.execution.reason
            $health.demo_order_sent = [bool]$demoResult.execution.order_sent
            $health.position_managed = [bool]$demoResult.management.position_managed
        }

        $lastSuccessUtc = [DateTime]::UtcNow.ToString("o")
        $health.ok = $true
        $health.last_success_utc = $lastSuccessUtc
        $health.quote_time = $result.quote_time
        $health.signal_stored = [bool]$result.signal_stored
    }
    catch {
        $health.error = $_.Exception.Message
        Add-Content -Path $LogPath -Value "[$attemptUtc] ERROR $($health.error)" -Encoding UTF8
    }
    $health | ConvertTo-Json -Depth 5 | Set-Content -Path $HealthTemp -Encoding UTF8
    Move-Item -Path $HealthTemp -Destination $HealthPath -Force
    if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
} while (-not $Once)

if (-not $health.ok) { exit 1 }
exit 0
