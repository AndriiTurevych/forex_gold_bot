[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$TerminalPath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Path $PSScriptRoot -Parent
}
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Installer = Join-Path $RepoRoot "scripts\install_midas_v2_ea.py"

if (-not (Test-Path $Python)) { throw "PYTHON_NOT_FOUND:$Python" }
if (-not (Test-Path $Installer)) { throw "EA_INSTALLER_NOT_FOUND:$Installer" }

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

Push-Location $RepoRoot
try {
    & $Python $Installer --terminal-path $TerminalPath
    if ($LASTEXITCODE -ne 0) { throw "MIDAS_EA_INSTALL_FAILED:$LASTEXITCODE" }
}
finally {
    Pop-Location
}
