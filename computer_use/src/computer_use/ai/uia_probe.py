"""Optional UIA element discovery (Windows + pywinauto); no-op elsewhere."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class UiaElement:
    name: str
    control_type: str
    center_x: int
    center_y: int


def list_uia_elements_for_hwnd(hwnd: int | None, *, limit: int = 40) -> list[UiaElement]:
    if not hwnd or hwnd <= 0 or sys.platform != "win32":
        return []
    try:
        from pywinauto import Application  # type: ignore[import-untyped]
    except ImportError:
        return []
    try:
        app = Application(backend="uia").connect(handle=hwnd, timeout=1)
        window = app.window(handle=hwnd)
        out: list[UiaElement] = []
        for ctrl in window.descendants():
            if len(out) >= limit:
                break
            name = (ctrl.window_text() or "").strip()
            if not name:
                continue
            try:
                rect = ctrl.rectangle()
                cx = int((rect.left + rect.right) / 2)
                cy = int((rect.top + rect.bottom) / 2)
            except Exception:
                continue
            ctype = str(getattr(ctrl, "friendly_class_name", "") or "Control")
            out.append(
                UiaElement(name=name, control_type=ctype, center_x=cx, center_y=cy)
            )
        return out
    except Exception:
        return []
