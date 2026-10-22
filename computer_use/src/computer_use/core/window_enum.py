from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    is_visible: bool = True


class WindowEnumerator(ABC):
    @abstractmethod
    def list_windows(self) -> list[WindowInfo]:
        raise NotImplementedError

    @abstractmethod
    def focus_window(self, handle: int) -> bool:
        raise NotImplementedError


class StubWindowEnumerator(WindowEnumerator):
    """Non-Windows stub for CI and development."""

    def list_windows(self) -> list[WindowInfo]:
        return [
            WindowInfo(handle=0, title="(stub) No windows — run on Windows for real enumeration"),
        ]

    def focus_window(self, handle: int) -> bool:
        return handle == 0


class Win32WindowEnumerator(WindowEnumerator):
    def list_windows(self) -> list[WindowInfo]:
        import win32gui  # type: ignore[import-untyped]

        results: list[WindowInfo] = []

        def callback(hwnd: int, _: int) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title.strip():
                return True
            results.append(
                WindowInfo(handle=int(hwnd), title=title, is_visible=True)
            )
            return True

        win32gui.EnumWindows(callback, 0)
        results.sort(key=lambda w: w.title.lower())
        return results

    def focus_window(self, handle: int) -> bool:
        import win32gui  # type: ignore[import-untyped]
        import win32con  # type: ignore[import-untyped]

        try:
            win32gui.ShowWindow(handle, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(handle)
            return True
        except Exception:
            return False


def get_window_enumerator() -> WindowEnumerator:
    if sys.platform == "win32":
        try:
            return Win32WindowEnumerator()
        except ImportError:
            return StubWindowEnumerator()
    return StubWindowEnumerator()
