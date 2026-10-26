# Computer Use (Windows automation)

VOC Tracker repo 내 **독립 Python 패키지**. 기존 Node/Apps Script 앱과 무관.

## Quick start

| Phase | Capability |
|-------|------------|
| 1 | Capture, region, input, policy, GUI shell |
| 1.5 | Closed-loop agent (`agent/loop.py`), ledger, §13 tests |
| 2 | Edge HWND attach, MFA auth pause (no browser launch) |
| 3 | RDP/Citrix/Horizon window + relative coordinate loop |
| 4 | Ollama planner/interpret hooks (`ai/`, `agents/pipeline.py`) |
| 5 | Teach & Replay + Glean reference helper (`workflow/`) |

**Closed-loop (GUI):** natural-language goal → Start; ledger at `~/.computer_use/agent_ledger.json`. **Teach & Replay:** enable panel toggle → record → save JSON under `~/.computer_use/workflows/`.

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

Default pytest excludes `@pytest.mark.windows` tests (`addopts = -m "not windows"` in `pyproject.toml`).

| Command | Where | Purpose |
|---------|-------|---------|
| `pytest` or `pytest -m "not windows"` | Linux CI / dev | Unit tests + §13 closed-loop (no Win32) |
| `pytest -m windows` | Windows PC | Win32 enumeration, PySide6 import smoke |
| `pytest -m ""` | Windows (optional) | Full suite including Windows-marked tests |

GUI and real window handles require Windows manual testing — Project store `docs/windows-validation-checklist.md` (§11 + closed-loop GUI).

**CU-5 automated validation (Windows):** `computer_use/scripts/run_cu5_validation.ps1` — pytest, structured checks, `cu5-validation-report.json`.

**User manual (KO):** [`docs/user-manual.md`](docs/user-manual.md) (repo) · Project store [`docs/user-manual.md`](/cursor/stores/self/docs/user-manual.md) — install, CU-5 auto run, modes, Teach & Replay, troubleshooting.

## Security

- No auth bypass, no cookie/token extraction APIs.
- Do **not** add Edge `launch()` or CDP unless explicitly approved; Browser mode must attach to existing windows only (Phase 2).
- Optional: `COMPUTER_USE_ALLOW_CDP=1` only with explicit operator opt-in.
- External LLM: requires `COMPUTER_USE_ALLOW_EXTERNAL_LLM=1` (default localhost Ollama only).

## Layout (§9)

- `src/computer_use/core/` — capture, input, windows, regions, validator
- `src/computer_use/policy/` — policy_guard
- `src/computer_use/agent/` — closed-loop types, ledger, adapters, `run_computer_use`
- `src/computer_use/controllers/` — browser (Edge), remote (RDP/Citrix)
- `src/computer_use/vision/` — coordinate mapper, screen diff, template match
- `src/computer_use/gui/` — PySide6 shell, closed-loop controller, teach/replay panel
- `src/computer_use/modes/` — local, browser, remote mode wiring
- `src/computer_use/agents/` — pipeline facade (`AgentPipeline`)
- `src/computer_use/ai/` — Phase 4 local LLM (Ollama), planner, interpret cache, extended validator
- `src/computer_use/workflow/` — Teach & Replay recorder/replay, Glean helper (reference-only)

## Phase 4 — Local LLM (Ollama)

Planner/Perception only; executor stays coordinate/policy deterministic.

| Env | Default | Meaning |
|-----|---------|---------|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama base URL |
| `COMPUTER_USE_AI_ENABLED` | `1` | `0` → stub interpret/plan |
| `COMPUTER_USE_ALLOW_EXTERNAL_LLM` | off | `1` → allow non-localhost LLM (company data) |
| `COMPUTER_USE_VISION` | off | `1` → optional vision model hook (never text-only as vision) |
| `COMPUTER_USE_OLLAMA_TEXT_MODEL` | auto | Override text planner model name |
| `LLAMA_CPP_SERVER_URL` | probe | Optional llama.cpp server |
| `COMPUTER_USE_VERIFY_FILE` | — | `result_query` file-exists hook (tests/dev) |

**Windows manual:** install [Ollama](https://ollama.com/download), `ollama pull llama3.2` (and optional `llava` for vision). GUI shows model status on startup.
