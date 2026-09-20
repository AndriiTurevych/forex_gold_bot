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

function Set-MidasEnv([string]$Name,[string]$Value) {
    [Environment]::SetEnvironmentVariable($Name,$Value,"User")
    Set-Item -Path ("Env:" + $Name) -Value $Value
}

Push-Location $RepoRoot
try {
    git fetch origin
    git checkout midas-v2-ai-gate
    git pull origin midas-v2-ai-gate

    Set-MidasEnv "MIDAS_AI_GATE_ENABLED" "1"
    Set-MidasEnv "MIDAS_OPENAI_MODEL" "gpt-5.6-sol"
    Set-MidasEnv "MIDAS_EA_COMMAND_ENABLED" "1"
    Set-MidasEnv "MIDAS_DEMO_EXECUTION_ENABLED" "0"
    Set-MidasEnv "MIDAS_MAX_RISK_FRACTION" "0.0025"
    Set-MidasEnv "MIDAS_MAX_DAILY_LOSS_FRACTION" "0.01"
    Set-MidasEnv "MIDAS_MAX_CONSECUTIVE_LOSSES" "3"
    Set-MidasEnv "MIDAS_MAX_OPEN_POSITIONS" "1"
    Set-MidasEnv "MIDAS_MIN_RR_TP2" "1.8"
    Set-MidasEnv "MIDAS_MIN_CONFIDENCE_SCORE" "60"
    Set-MidasEnv "MIDAS_MAX_SPREAD_POINTS" "80"
    Set-MidasEnv "MIDAS_EA_COMMAND_TTL_SECONDS" "90"

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
    if ([string]::IsNullOrWhiteSpace($env:MIDAS_INGEST_TOKEN) -and -not [string]::IsNullOrWhiteSpace($ingest)) {
        $env:MIDAS_INGEST_TOKEN = $ingest
    }
    if ([string]::IsNullOrWhiteSpace($env:MIDAS_INGEST_TOKEN)) {
        throw "MIDAS_INGEST_TOKEN_NOT_SET"
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_midas_v2_ea.ps1" -RepoRoot $RepoRoot -TerminalPath $TerminalPath
    if ($LASTEXITCODE -ne 0) { throw "EA_INSTALL_FAILED" }

    if ($Mode -eq "DemoEA") {
        & $Python ".\scripts\backtest_midas_crt_tbs_mt5.py" --terminal-path $TerminalPath --days 365
        if ($LASTEXITCODE -ne 0) { throw "STRUCTURAL_BACKTEST_FAILED" }
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\repair_midas_mt5_bridge.ps1" -RepoRoot $RepoRoot -TerminalPath $TerminalPath
    if ($LASTEXITCODE -ne 0) { throw "BRIDGE_INSTALL_FAILED" }

    # The EA may not yet be attached to a chart. Verify the control plane and
    # live OpenAI structured-output path now; final DEMO preflight follows attach.
    $preflightArgs = @(".\scripts\preflight_midas_v2.py","--terminal-path",$TerminalPath,"--probe-openai")
    & $Python @preflightArgs
    $preflightExit = $LASTEXITCODE

    Write-Host ""
    Write-Host "MIDAS 2.0 files installed."
    Write-Host "Attach MIDAS_V2_DemoEA to XAUUSD M5."
    Write-Host "The EA will create Profiles\Templates\MIDAS_V2_XAUUSD.tpl while DemoExecution is OFF."
    if ($Mode -eq "DemoEA") {
        Write-Host "Structural backtest artifacts: mt5_artifacts\backtest_crt_tbs"
        Write-Host "After attaching the EA, run the final DEMO preflight:"
        Write-Host "  .\.venv\Scripts\python.exe .\scripts\preflight_midas_v2.py --terminal-path <terminal64.exe> --probe-openai --require-demo"
        Write-Host "Only when ready_for_demo_ea=true, set InpEnableDemoExecution=true."
    } else {
        Write-Host "Keep InpEnableDemoExecution=false for shadow mode."
    }
    exit $preflightExit
}
finally {
    Pop-Location
}
