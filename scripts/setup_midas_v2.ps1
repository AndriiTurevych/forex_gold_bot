[CmdletBinding()]
param(
    [ValidateSet("Shadow","DemoEA")]
    [string]$Mode = "Shadow",
    [string]$RepoRoot,
    [string]$TerminalPath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Path $PSScriptRoot -Parent
}
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)

if ([string]::IsNullOrWhiteSpace($TerminalPath)) {
    $process = Get-Process terminal64 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($process -and $process.Path) { $TerminalPath = $process.Path }
}
if ([string]::IsNullOrWhiteSpace($TerminalPath)) {
    $candidate = Join-Path $env:APPDATA "MetaTrader 5\terminal64.exe"
    if (Test-Path $candidate) { $TerminalPath = $candidate }
}
if ([string]::IsNullOrWhiteSpace($TerminalPath) -or -not (Test-Path $TerminalPath)) {
    throw "OPEN_MT5_OR_PASS_TERMINAL_PATH"
}

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "PYTHON_NOT_FOUND:$Python" }

Push-Location $RepoRoot
try {
    git fetch origin
    git checkout midas-v2-ai-gate
    git pull origin midas-v2-ai-gate

    [Environment]::SetEnvironmentVariable("MIDAS_AI_GATE_ENABLED","1","User")
    [Environment]::SetEnvironmentVariable("MIDAS_OPENAI_MODEL","gpt-5.6-sol","User")
    [Environment]::SetEnvironmentVariable("MIDAS_EA_COMMAND_ENABLED","1","User")
    [Environment]::SetEnvironmentVariable("MIDAS_DEMO_EXECUTION_ENABLED","0","User")
    [Environment]::SetEnvironmentVariable("MIDAS_MAX_RISK_FRACTION","0.0025","User")
    [Environment]::SetEnvironmentVariable("MIDAS_MAX_DAILY_LOSS_FRACTION","0.01","User")
    [Environment]::SetEnvironmentVariable("MIDAS_MAX_CONSECUTIVE_LOSSES","3","User")
    [Environment]::SetEnvironmentVariable("MIDAS_MAX_OPEN_POSITIONS","1","User")
    [Environment]::SetEnvironmentVariable("MIDAS_MIN_RR_TP2","1.8","User")
    [Environment]::SetEnvironmentVariable("MIDAS_MIN_CONFIDENCE_SCORE","60","User")
    [Environment]::SetEnvironmentVariable("MIDAS_MAX_SPREAD_POINTS","80","User")
    [Environment]::SetEnvironmentVariable("MIDAS_EA_COMMAND_TTL_SECONDS","90","User")

    $apiKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY","User")
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        $sec = Read-Host "OpenAI API key" -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try {
            $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
            [Environment]::SetEnvironmentVariable("OPENAI_API_KEY",$plain,"User")
            $env:OPENAI_API_KEY = $plain
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
    } else {
        $env:OPENAI_API_KEY = $apiKey
    }

    $ingest = [Environment]::GetEnvironmentVariable("MIDAS_INGEST_TOKEN","User")
    if ([string]::IsNullOrWhiteSpace($ingest) -and [string]::IsNullOrWhiteSpace($env:MIDAS_INGEST_TOKEN)) {
        throw "MIDAS_INGEST_TOKEN_NOT_SET"
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_midas_v2_ea.ps1" -RepoRoot $RepoRoot -TerminalPath $TerminalPath
    if ($LASTEXITCODE -ne 0) { throw "EA_INSTALL_FAILED" }

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\repair_midas_mt5_bridge.ps1" -RepoRoot $RepoRoot -TerminalPath $TerminalPath
    if ($LASTEXITCODE -ne 0) { throw "BRIDGE_INSTALL_FAILED" }

    $preflightArgs = @(".\scripts\preflight_midas_v2.py","--terminal-path",$TerminalPath)
    if ($Mode -eq "DemoEA") { $preflightArgs += "--require-demo" }
    & $Python @preflightArgs
    $preflightExit = $LASTEXITCODE

    Write-Host ""
    Write-Host "MIDAS 2.0 files installed."
    Write-Host "Attach MIDAS_V2_DemoEA to XAUUSD M5."
    Write-Host "The EA will create Profiles\Templates\MIDAS_V2_XAUUSD.tpl while DemoExecution is OFF."
    if ($Mode -eq "DemoEA") {
        Write-Host "After preflight is green on a DEMO account, set InpEnableDemoExecution=true in EA inputs."
    } else {
        Write-Host "Keep InpEnableDemoExecution=false for shadow mode."
    }
    exit $preflightExit
}
finally {
    Pop-Location
}
