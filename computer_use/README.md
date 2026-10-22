# Computer Use (Windows automation)

VOC Tracker repo 내 **독립 Python 패키지**. 기존 Node/Apps Script 앱과 무관.

## Phase 1 scope

- Window enumeration (Windows: Win32, Linux: stub for tests)
- Region model + optional PySide6 region selector
- Screen capture (`mss`)
- Mouse/keyboard (`pynput`) with `policy_guard`
- Result validation (image hash / similarity)

## Windows setup

```powershell
cd computer_use
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui,windows,dev]"
pytest
python -m computer_use.gui.app
```

## Linux / CI (limited)

```bash
cd computer_use
pip install -e ".[dev]"
pytest
```

GUI and real window handles require Windows manual testing (see Project `docs/gap-analysis.md` §11).

## Security

- No auth bypass, no cookie/token extraction APIs.
- Do **not** add Edge `launch()` or CDP unless explicitly approved; Browser mode must attach to existing windows only (Phase 2).

## Layout (§9)

- `src/computer_use/core/` — capture, input, windows, regions, validator
- `src/computer_use/policy/` — policy_guard
- `src/computer_use/gui/` — PySide6 shell (KO/EN strings)
- `src/computer_use/modes/` — local/browser/remote stubs
- `src/computer_use/agents/` — planner pipeline stubs
