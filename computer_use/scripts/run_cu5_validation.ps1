# CU-5 automated Windows validation entry point.
param(
    [string] $OutputDir = "",
    [switch] $SkipInstall,
    [switch] $SkipSmoke,
    [switch] $IncludeGui
)

$ErrorActionPreference = "Stop"

if (-not $IsWindows -and $env:OS -ne "Windows_NT") {
    Write-Error @"
run_cu5_validation.ps1 requires Windows (Win32 smoke, pytest -m windows).
On Linux CI use: pytest -m `"not windows`" and unit tests in tests/test_cu5_validation.py
"@
    exit 2
}

$PkgRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $PkgRoot
if ($OutputDir -eq "") {
    $OutputDir = Get-Location
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Set-Location $PkgRoot

$InstallOk = $true
if (-not $SkipInstall) {
    Write-Host "== CU-5: venv + pip install =="
    if (-not (Test-Path ".venv")) {
        python -m venv .venv
    }
    & .\.venv\Scripts\Activate.ps1
    python -m pip install -U pip wheel
    pip install -e ".[gui,windows,dev]"
    if ($LASTEXITCODE -ne 0) {
        $InstallOk = $false
    }
} else {
    & .\.venv\Scripts\Activate.ps1
}

$SmokeExit = $null
$SmokeScript = Join-Path $RepoRoot "scripts\run_windows_smoke.ps1"
if (-not $SkipSmoke -and (Test-Path $SmokeScript)) {
    Write-Host "== CU-5: run_windows_smoke.ps1 =="
    & $SmokeScript
    $SmokeExit = $LASTEXITCODE
}

$LogNotWindows = Join-Path $OutputDir "pytest-not-windows.log"
$LogWindows = Join-Path $OutputDir "pytest-windows.log"
$JunitNotWindows = Join-Path $OutputDir "junit-not-windows.xml"
$JunitWindows = Join-Path $OutputDir "junit-windows.xml"

Write-Host "== CU-5: pytest -m `"not windows`" =="
pytest -m "not windows" --tb=short --junitxml $JunitNotWindows 2>&1 | Tee-Object -FilePath $LogNotWindows
$PytestNotWindowsExit = $LASTEXITCODE

Write-Host "== CU-5: pytest -m windows =="
pytest -m windows --tb=short --junitxml $JunitWindows 2>&1 | Tee-Object -FilePath $LogWindows
$PytestWindowsExit = $LASTEXITCODE

$RunnerArgs = @(
    "-m", "computer_use.validation.cu5_runner",
    "--output-dir", $OutputDir,
    "--pkg-root", $PkgRoot,
    "--pytest-not-windows-log", $LogNotWindows,
    "--pytest-windows-log", $LogWindows,
    "--junit-not-windows", $JunitNotWindows,
    "--junit-windows", $JunitWindows
)
if ($InstallOk) {
    $RunnerArgs += "--install-ok"
} else {
    $RunnerArgs += "--install-failed"
}
if ($null -ne $SmokeExit) {
    $RunnerArgs += @("--smoke-exit-code", [string]$SmokeExit)
}
$RunnerArgs += @(
    "--pytest-not-windows-exit", [string]$PytestNotWindowsExit,
    "--pytest-windows-exit", [string]$PytestWindowsExit
)
if ($IncludeGui) {
    $RunnerArgs += "--include-gui"
}

Write-Host "== CU-5: structured runner =="
python @RunnerArgs
$RunnerExit = $LASTEXITCODE

Write-Host ""
Write-Host "Reports: $(Join-Path $OutputDir 'cu5-validation-report.json')"
Write-Host "         $(Join-Path $OutputDir 'cu5-validation-report.md')"
Write-Host "Paste block: python -m computer_use.validation.cu5_runner --from-report $(Join-Path $OutputDir 'cu5-validation-report.json') --print-paste-block"

if ($RunnerExit -ne 0) {
    exit $RunnerExit
}
if ($PytestNotWindowsExit -ne 0 -or $PytestWindowsExit -ne 0) {
    exit 1
}
if ($null -ne $SmokeExit -and $SmokeExit -ne 0) {
    exit 1
}
exit 0
