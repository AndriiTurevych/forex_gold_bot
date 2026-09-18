[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$TerminalPath,
    [ValidateRange(15, 3600)]
    [int]$IntervalSeconds = 60,
    [string]$IngestUrl
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Path $PSScriptRoot -Parent
}
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$Install = Join-Path $RepoRoot "scripts\install_midas_mt5_bridge.ps1"
$Check = Join-Path $RepoRoot "scripts\check_midas_mt5_bridge.ps1"
$HealthPath = Join-Path $RepoRoot "mt5_artifacts\health.json"
$LogPath = Join-Path $RepoRoot "mt5_artifacts\bridge.log"

if (-not (Test-Path $Install)) { throw "INSTALL_SCRIPT_NOT_FOUND:$Install" }
if (-not (Test-Path $Check)) { throw "CHECK_SCRIPT_NOT_FOUND:$Check" }

try {
    $installArgs = @{
        RepoRoot = $RepoRoot
        IntervalSeconds = $IntervalSeconds
    }
    if (-not [string]::IsNullOrWhiteSpace($TerminalPath)) { $installArgs.TerminalPath = $TerminalPath }
    if (-not [string]::IsNullOrWhiteSpace($IngestUrl)) { $installArgs.IngestUrl = $IngestUrl }

    & $Install @installArgs
    & $Check -RepoRoot $RepoRoot
}
catch {
    Write-Error $_.Exception.Message
    if (Test-Path $HealthPath) {
        Write-Host "---- health.json ----"
        Get-Content $HealthPath -Raw
    }
    if (Test-Path $LogPath) {
        Write-Host "---- bridge.log (last 40 lines) ----"
        Get-Content $LogPath -Tail 40
    }
    exit 1
}
