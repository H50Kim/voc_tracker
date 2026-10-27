"""User data paths for ledger persistence."""

from __future__ import annotations

from pathlib import Path


def user_data_dir() -> Path:
    base = Path.home() / ".computer_use"
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_ledger_path() -> Path:
    return user_data_dir() / "agent_ledger.json"
