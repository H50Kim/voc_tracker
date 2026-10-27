# Print CU-5 paste block and optional copy hint for Project store results doc.
param(
    [Parameter(Mandatory = $true)]
    [string] $ReportJson,
    [switch] $PrintOnly
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ReportJson)) {
    Write-Error "Report not found: $ReportJson"
    exit 1
}

$PkgRoot = Split-Path -Parent $PSScriptRoot
Set-Location $PkgRoot
& .\.venv\Scripts\Activate.ps1

Write-Host "=== CU-5 paste block (cu5-results-paste-template) ==="
python -m computer_use.validation.cu5_runner --from-report $ReportJson --print-paste-block

if (-not $PrintOnly) {
    Write-Host ""
    Write-Host "Next: attach cu5-validation-report.json to Project store docs/windows-validation-results.md"
    Write-Host "      and paste the block above into chat for the Coordinator."
}
