# Windows smoke: install deps, import smoke, run pytest (non-GUI + windows-marked).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Pkg = Join-Path $Root "computer_use"

Set-Location $Pkg

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install -U pip wheel
pip install -e ".[gui,windows,dev]"

Write-Host "== Import smoke =="
python -c @"
import computer_use
from computer_use.core.window_enum import get_window_enumerator
from computer_use.agent.loop import run_computer_use
wins = get_window_enumerator().list_windows()
print(f'windows listed: {len(wins)}')
"@

Write-Host "== pytest (Linux-parity, no windows marker) =="
pytest -m "not windows"

Write-Host "== pytest (windows-marked integration) =="
pytest -m windows

Write-Host "Smoke complete. For GUI E2E use docs/windows-validation-checklist.md in the Project store."
