"""Windows-only integration smoke (Win32, optional GUI). Not collected on Linux CI by default."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.windows


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_smoke_core_imports_on_windows():
    from computer_use.core import capture, input_control, region, validator, window_enum  # noqa: F401
    from computer_use.policy import policy_guard  # noqa: F401
    from computer_use.agent import loop  # noqa: F401


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_win32_window_enumerator_lists_real_handles():
    from computer_use.core.window_enum import Win32WindowEnumerator

    enum = Win32WindowEnumerator()
    wins = enum.list_windows()
    assert len(wins) >= 1
    assert all(w.handle > 0 for w in wins)
    assert all("(stub)" not in w.title for w in wins)


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_get_window_enumerator_uses_win32_when_pywin32_present():
    from computer_use.core.window_enum import Win32WindowEnumerator, get_window_enumerator

    enum = get_window_enumerator()
    assert isinstance(enum, Win32WindowEnumerator)


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_pyside6_gui_import():
    pytest.importorskip("PySide6")
    from computer_use.gui.main_window import MainWindow  # noqa: F401

    assert MainWindow is not None
