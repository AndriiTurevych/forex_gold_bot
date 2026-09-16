[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [Parameter(Mandatory = $true)]
    [string]$TerminalPath,
    [ValidateRange(15, 3600)]
    [int]$IntervalSeconds = 60,
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

New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null
if (-not (Test-Path $Python)) { throw "PYTHON_NOT_FOUND:$Python" }
if (-not (Test-Path $SyncScript)) { throw "SYNC_SCRIPT_NOT_FOUND:$SyncScript" }
if (-not (Test-Path $TerminalPath)) { throw "MT5_TERMINAL_NOT_FOUND:$TerminalPath" }

$savedToken = [Environment]::GetEnvironmentVariable("MIDAS_INGEST_TOKEN", "User")
if (-not $env:MIDAS_INGEST_TOKEN -and $savedToken) {
    $env:MIDAS_INGEST_TOKEN = $savedToken
}
if (-not $env:MIDAS_INGEST_TOKEN) { throw "MIDAS_INGEST_TOKEN_NOT_SET" }
$env:PYTHONPATH = $RepoRoot

$lastSuccessUtc = $null
if (Test-Path $HealthPath) {
    try { $lastSuccessUtc = (Get-Content $HealthPath -Raw | ConvertFrom-Json).last_success_utc } catch {}
}

do {
    $attemptUtc = [DateTime]::UtcNow.ToString("o")
    $health = [ordered]@{
        ok = $false
        task = "MIDAS MT5 Bridge"
        attempted_at_utc = $attemptUtc
        last_success_utc = $lastSuccessUtc
        quote_time = $null
        signal_stored = $false
        error = $null
        real_orders_allowed = $false
    }
    try {
        $arguments = @(
            $SyncScript,
            "--terminal-path", $TerminalPath,
            "--server-utc-offset-hours", "3",
            "--mt5-timeout-ms", "10000"
        )
        $lines = @(& $Python @arguments 2>&1 | ForEach-Object { "$_" })
        $exitCode = $LASTEXITCODE
        foreach ($line in $lines) { Add-Content -Path $LogPath -Value "[$attemptUtc] $line" -Encoding UTF8 }
        if ($exitCode -ne 0) { throw "SYNC_EXIT_$exitCode" }
        $result = $lines[-1] | ConvertFrom-Json
        if ($result.ok -ne $true) { throw "SYNC_RESULT_NOT_OK" }
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
    $health | ConvertTo-Json -Depth 4 | Set-Content -Path $HealthTemp -Encoding UTF8
    Move-Item -Path $HealthTemp -Destination $HealthPath -Force
    if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
} while (-not $Once)

if (-not $health.ok) { exit 1 }
exit 0
