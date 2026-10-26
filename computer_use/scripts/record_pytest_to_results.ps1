# Appends a markdown fragment (stdout) summarizing the last pytest run for CU-5 results paste.
# Usage:
#   cd computer_use
#   .\scripts\record_pytest_to_results.ps1 -Command 'pytest -m "not windows"'
#   .\scripts\record_pytest_to_results.ps1 -Command 'pytest -m windows' -Label auto-windows
param(
    [string]$Command = 'pytest -m "not windows"',
    [string]$Label = 'auto-not-windows',
    [string]$LogPath = ''
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PkgRoot = Split-Path -Parent $ScriptDir
Set-Location $PkgRoot

$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$logFile = if ($LogPath) { $LogPath } else { Join-Path $env:TEMP "cu5-pytest-$Label.log" }

Write-Host "Running: $Command" -ForegroundColor Cyan
Write-Host "Log: $logFile"

$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& cmd.exe /c "$Command 2>&1" | Tee-Object -FilePath $logFile
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap

$tail = Get-Content -Path $logFile -Tail 80 -ErrorAction SilentlyContinue
$summaryLine = $tail | Select-String -Pattern '(\d+) passed' | Select-Object -Last 1
$passed = $null
$failed = $null
$skipped = $null
$deselected = $null
$errorCount = $null

if ($summaryLine) {
    $s = $summaryLine.Line
    if ($s -match '(\d+) passed') { $passed = $Matches[1] }
    if ($s -match '(\d+) failed') { $failed = $Matches[1] }
    if ($s -match '(\d+) skipped') { $skipped = $Matches[1] }
    if ($s -match '(\d+) deselected') { $deselected = $Matches[1] }
    if ($s -match '(\d+) error') { $errorCount = $Matches[1] }
}

$counts = @()
if ($null -ne $passed) { $counts += "$passed passed" }
if ($null -ne $failed) { $counts += "$failed failed" }
if ($null -ne $skipped) { $counts += "$skipped skipped" }
if ($null -ne $deselected) { $counts += "$deselected deselected" }
if ($null -ne $errorCount) { $counts += "$errorCount error" }
$countText = if ($counts.Count -gt 0) { $counts -join ', ' } else { 'summary not parsed' }

$resultHint = if ($exitCode -eq 0) { 'Pass' } else { 'Fail' }

Write-Output ''
Write-Output '--- CU-5 pytest fragment (paste into chat or results doc) ---'
Write-Output "${Label}: $resultHint | $logFile | $countText @ $timestamp"
Write-Output ''
Write-Output '| Passed | Failed | Skipped | Exit |'
Write-Output "| $(if ($null -ne $passed) { $passed } else { '' }) | $(if ($null -ne $failed) { $failed } else { '' }) | $(if ($null -ne $skipped) { $skipped } else { '' }) | $exitCode |"

exit $exitCode
