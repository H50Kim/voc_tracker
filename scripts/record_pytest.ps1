# Record pytest output for CU-5 evidence (Windows).
param(
    [ValidateSet("not-windows", "windows", "full")]
    [string] $Marker = "not-windows"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Pkg = Join-Path $Root "computer_use"
$OutDir = if ($env:CU5_EVIDENCE_DIR) { $env:CU5_EVIDENCE_DIR } else { Join-Path $Root "evidence\pytest" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Set-Location $Pkg

if (-not (Test-Path ".venv")) {
    Write-Host "No .venv in computer_use; activate your venv or run run_windows_smoke.ps1 first."
}

switch ($Marker) {
    "not-windows" {
        $Out = Join-Path $OutDir "pytest-not-windows.log"
        Write-Host "Running: pytest -m `"not windows`" -> $Out"
        pytest -m "not windows" 2>&1 | Tee-Object -FilePath $Out
    }
    "windows" {
        $Out = Join-Path $OutDir "pytest-windows.log"
        Write-Host "Running: pytest -m windows -> $Out"
        pytest -m windows 2>&1 | Tee-Object -FilePath $Out
    }
    "full" {
        $Out = Join-Path $OutDir "pytest-full.log"
        Write-Host "Running: pytest -> $Out"
        pytest 2>&1 | Tee-Object -FilePath $Out
    }
}

Write-Host "Saved: $Out"
