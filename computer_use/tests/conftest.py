"""Shared pytest configuration for computer_use tests."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "windows: tests that require Windows (Win32, GUI display, or real input)",
    )
