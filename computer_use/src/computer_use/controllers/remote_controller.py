"""Attach to remote desktop client windows (RDP / Citrix / VMware Horizon).

Image-first automation: no UIA inside the remote session, no agent install on remote VM.
"""

from __future__ import annotations

import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from PIL import Image, ImageStat

from computer_use.controllers.browser_controller import intersect_capture_region
from computer_use.core.region import ScreenRegion
from computer_use.vision.coordinate_mapper import (
    CoordinateMapper,
    RemoteSurfaceBinding,
    screen_drag_to_inner_relative,
)


class RemoteClientKind(str, Enum):
    RDP = "rdp"
    CITRIX = "citrix"
    HORIZON = "horizon"
    UNKNOWN = "unknown"


# --- Heuristics (Windows host client chrome only) ---

_REMOTE_TITLE_PATTERNS: tuple[tuple[re.Pattern[str], RemoteClientKind], ...] = (
    (re.compile(r"remote\s+desktop", re.I), RemoteClientKind.RDP),
    (re.compile(r"azure\s+virtual\s+desktop", re.I), RemoteClientKind.RDP),
    (re.compile(r"\bavd\b", re.I), RemoteClientKind.RDP),
    (re.compile(r"citrix\s+workspace", re.I), RemoteClientKind.CITRIX),
    (re.compile(r"citrix\s+receiver", re.I), RemoteClientKind.CITRIX),
    (re.compile(r"vmware\s+horizon", re.I), RemoteClientKind.HORIZON),
    (re.compile(r"horizon\s+client", re.I), RemoteClientKind.HORIZON),
)

_DISCONNECT_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"disconnected", re.I),
    re.compile(r"reconnect", re.I),
    re.compile(r"connection\s+lost", re.I),
    re.compile(r"session\s+ended", re.I),
    re.compile(r"unable\s+to\s+connect", re.I),
)

_LOCK_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"windows\s+security", re.I),
    re.compile(r"\blocked\b", re.I),
    re.compile(r"sign\s*in\s+to\s+unlock", re.I),
)

_RDP_EXE = frozenset({"msrdc.exe", "mstsc.exe", "rdpclip.exe"})
_CITRIX_EXE = frozenset({"wfica32.exe", "wfcrun32.exe", "receiver.exe", "selfservice.exe"})
_HORIZON_EXE = frozenset({"vmware-view.exe", "horizon-client.exe", "vmware-horizon-client.exe"})

_RDP_CLASSES = frozenset({"tscshellcontainerclass", "tscremotecontrolclass"})
_CITRIX_CLASSES = frozenset({"ctxwfcontclass", "ctxwfcframeclass"})


class SessionHealthAction(str, Enum):
    PAUSE = "pause"
    STOP = "stop"


@dataclass(frozen=True)
class RemoteWindowInfo:
    handle: int
    title: str
    client_kind: RemoteClientKind
    process_name: str = ""
    window_class: str = ""
    is_visible: bool = True


@dataclass(frozen=True)
class SessionHealthSignal:
    """Remote session unusable — pause or stop closed-loop (no bypass)."""

    reason: str
    action: SessionHealthAction
    matched_pattern: str = ""


def classify_remote_client(
    *,
    title: str,
    process_name: str = "",
    window_class: str = "",
) -> RemoteClientKind:
    proc = process_name.lower()
    wclass = window_class.lower()
    if proc in _RDP_EXE or wclass in _RDP_CLASSES:
        return RemoteClientKind.RDP
    if proc in _CITRIX_EXE or wclass in _CITRIX_CLASSES:
        return RemoteClientKind.CITRIX
    if proc in _HORIZON_EXE:
        return RemoteClientKind.HORIZON
    for pattern, kind in _REMOTE_TITLE_PATTERNS:
        if pattern.search(title):
            return kind
    if "citrix" in title.lower():
        return RemoteClientKind.CITRIX
    return RemoteClientKind.UNKNOWN


def detect_session_health_from_title(title: str) -> SessionHealthSignal | None:
    for pattern in _DISCONNECT_TITLE_PATTERNS:
        if pattern.search(title):
            return SessionHealthSignal(
                reason="Remote session disconnected or reconnect required.",
                action=SessionHealthAction.STOP,
                matched_pattern=pattern.pattern,
            )
    for pattern in _LOCK_TITLE_PATTERNS:
        if pattern.search(title):
            return SessionHealthSignal(
                reason="Remote session locked; unlock manually before continuing.",
                action=SessionHealthAction.PAUSE,
                matched_pattern=pattern.pattern,
            )
    return None


def detect_black_screen(image: Image.Image, *, mean_threshold: float = 8.0) -> bool:
    """Heuristic: nearly uniform dark frame (RDP disconnect / minimized content)."""
    rgb = image.convert("RGB")
    stat = ImageStat.Stat(rgb)
    mean_luma = sum(stat.mean[:3]) / 3.0
    if mean_luma > mean_threshold:
        return False
    # Also require low variance (uniform black/grey)
    var = sum(stat.var[:3]) / 3.0
    return var < 200.0


class RemoteWindowEnumerator(ABC):
    @abstractmethod
    def list_remote_windows(self) -> list[RemoteWindowInfo]:
        raise NotImplementedError

    @abstractmethod
    def get_window_rect(self, handle: int) -> ScreenRegion | None:
        raise NotImplementedError

    @abstractmethod
    def get_window_title(self, handle: int) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_window_minimized(self, handle: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_window_visible(self, handle: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def focus_window(self, handle: int) -> bool:
        raise NotImplementedError


class StubRemoteWindowEnumerator(RemoteWindowEnumerator):
    """Linux / CI fake RDP client window."""

    def list_remote_windows(self) -> list[RemoteWindowInfo]:
        return [
            RemoteWindowInfo(
                handle=9100,
                title="Contoso VM - Remote Desktop",
                client_kind=RemoteClientKind.RDP,
                process_name="msrdc.exe",
                window_class="TscShellContainerClass",
            )
        ]

    def get_window_rect(self, handle: int) -> ScreenRegion | None:
        if handle <= 0:
            return None
        return ScreenRegion(left=50, top=40, width=1024, height=768)

    def get_window_title(self, handle: int) -> str:
        for w in self.list_remote_windows():
            if w.handle == handle:
                return w.title
        return ""

    def is_window_minimized(self, handle: int) -> bool:
        return handle < 0

    def is_window_visible(self, handle: int) -> bool:
        return handle > 0

    def focus_window(self, handle: int) -> bool:
        return handle > 0


class Win32RemoteWindowEnumerator(RemoteWindowEnumerator):
    """Enumerate top-level remote client windows on Windows host."""

    def list_remote_windows(self) -> list[RemoteWindowInfo]:
        import win32gui  # type: ignore[import-untyped]
        import win32process  # type: ignore[import-untyped]

        results: list[RemoteWindowInfo] = []

        def callback(hwnd: int, _: int) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title.strip():
                return True
            try:
                wclass = win32gui.GetClassName(hwnd)
            except Exception:
                wclass = ""
            proc = self._exe_name_for_hwnd(hwnd)
            kind = classify_remote_client(title=title, process_name=proc, window_class=wclass)
            if kind == RemoteClientKind.UNKNOWN and not self._looks_like_remote(
                title, proc, wclass
            ):
                return True
            results.append(
                RemoteWindowInfo(
                    handle=int(hwnd),
                    title=title,
                    client_kind=kind,
                    process_name=proc,
                    window_class=wclass,
                    is_visible=True,
                )
            )
            return True

        win32gui.EnumWindows(callback, 0)
        results.sort(key=lambda w: w.title.lower())
        return results

    @staticmethod
    def _looks_like_remote(title: str, proc: str, wclass: str) -> bool:
        if proc in _RDP_EXE | _CITRIX_EXE | _HORIZON_EXE:
            return True
        if wclass.lower() in _RDP_CLASSES | _CITRIX_CLASSES:
            return True
        return classify_remote_client(title=title, process_name=proc, window_class=wclass) != (
            RemoteClientKind.UNKNOWN
        )

    @staticmethod
    def _exe_name_for_hwnd(hwnd: int) -> str:
        import win32api  # type: ignore[import-untyped]
        import win32con  # type: ignore[import-untyped]
        import win32process  # type: ignore[import-untyped]

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        access = win32con.PROCESS_QUERY_LIMITED_INFORMATION
        handle = win32api.OpenProcess(access, False, pid)
        try:
            exe_path = win32process.GetModuleFileNameEx(handle, 0)
        finally:
            win32api.CloseHandle(handle)
        return exe_path.rsplit("\\", 1)[-1].lower()

    def get_window_rect(self, handle: int) -> ScreenRegion | None:
        import win32gui  # type: ignore[import-untyped]

        try:
            left, top, right, bottom = win32gui.GetWindowRect(handle)
        except Exception:
            return None
        width = max(1, right - left)
        height = max(1, bottom - top)
        return ScreenRegion(left=int(left), top=int(top), width=width, height=height)

    def get_window_title(self, handle: int) -> str:
        import win32gui  # type: ignore[import-untyped]

        try:
            return win32gui.GetWindowText(handle)
        except Exception:
            return ""

    def is_window_minimized(self, handle: int) -> bool:
        import win32gui  # type: ignore[import-untyped]

        try:
            return bool(win32gui.IsIconic(handle))
        except Exception:
            return False

    def is_window_visible(self, handle: int) -> bool:
        import win32gui  # type: ignore[import-untyped]

        try:
            return bool(win32gui.IsWindowVisible(handle))
        except Exception:
            return False

    def focus_window(self, handle: int) -> bool:
        import win32con  # type: ignore[import-untyped]
        import win32gui  # type: ignore[import-untyped]

        try:
            win32gui.ShowWindow(handle, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(handle)
            return True
        except Exception:
            return False


def get_remote_enumerator() -> RemoteWindowEnumerator:
    if sys.platform == "win32":
        try:
            return Win32RemoteWindowEnumerator()
        except ImportError:
            return StubRemoteWindowEnumerator()
    return StubRemoteWindowEnumerator()


@dataclass
class RemoteController:
    """Remote desktop client attach helper (host-side window only)."""

    enumerator: RemoteWindowEnumerator | None = None

    def __post_init__(self) -> None:
        if self.enumerator is None:
            self.enumerator = get_remote_enumerator()

    def list_remote_windows(self) -> list[RemoteWindowInfo]:
        assert self.enumerator is not None
        return self.enumerator.list_remote_windows()

    def binding_from_gui_selection(
        self,
        *,
        window_handle: int,
        user_screen_region: ScreenRegion,
    ) -> RemoteSurfaceBinding | None:
        assert self.enumerator is not None
        window_rect = self.enumerator.get_window_rect(window_handle)
        if window_rect is None:
            return None
        inner = screen_drag_to_inner_relative(window_rect, user_screen_region)
        if inner is None:
            return None
        return RemoteSurfaceBinding(window_handle=window_handle, inner_relative=inner)

    def capture_region_for(
        self,
        *,
        window_handle: int | None,
        inner_relative: ScreenRegion | None,
        user_region: ScreenRegion | None,
    ) -> ScreenRegion | None:
        assert self.enumerator is not None
        if window_handle is None:
            return user_region
        window_region = self.enumerator.get_window_rect(window_handle)
        if window_region is None:
            return None
        if inner_relative is None:
            merged = intersect_capture_region(window_region, user_region)
            return merged
        inner_screen = ScreenRegion(
            left=window_region.left + inner_relative.left,
            top=window_region.top + inner_relative.top,
            width=inner_relative.width,
            height=inner_relative.height,
        )
        return intersect_capture_region(inner_screen, user_region)

    def coordinate_mapper(
        self,
        *,
        window_handle: int,
        inner_relative: ScreenRegion,
        user_region: ScreenRegion | None = None,
    ) -> CoordinateMapper | None:
        assert self.enumerator is not None
        window_rect = self.enumerator.get_window_rect(window_handle)
        if window_rect is None:
            return None
        binding = RemoteSurfaceBinding(window_handle=window_handle, inner_relative=inner_relative)
        return CoordinateMapper.from_binding(
            window_rect=window_rect,
            binding=binding,
            user_screen_region=user_region,
        )

    def refresh_mapper(
        self,
        handle: int,
        mapper: CoordinateMapper,
    ) -> CoordinateMapper | None:
        assert self.enumerator is not None
        window_rect = self.enumerator.get_window_rect(handle)
        if window_rect is None:
            return None
        return mapper.refresh_window_rect(window_rect)

    def check_session_health(
        self,
        handle: int | None,
        *,
        latest_capture: Image.Image | None = None,
    ) -> SessionHealthSignal | None:
        if not handle:
            return SessionHealthSignal(
                reason="No remote window selected.",
                action=SessionHealthAction.STOP,
            )
        assert self.enumerator is not None
        if not self.enumerator.is_window_visible(handle):
            return SessionHealthSignal(
                reason="Remote client window is not visible (closed or disconnected).",
                action=SessionHealthAction.STOP,
            )
        if self.enumerator.is_window_minimized(handle):
            return SessionHealthSignal(
                reason="Remote client window is minimized; restore it to continue.",
                action=SessionHealthAction.PAUSE,
            )
        title = self.enumerator.get_window_title(handle)
        title_signal = detect_session_health_from_title(title)
        if title_signal is not None:
            return title_signal
        if latest_capture is not None and detect_black_screen(latest_capture):
            return SessionHealthSignal(
                reason="Remote surface appears blank (black screen); check session.",
                action=SessionHealthAction.PAUSE,
            )
        return None

    def focus(self, handle: int) -> bool:
        assert self.enumerator is not None
        return self.enumerator.focus_window(handle)


def default_remote_controller() -> RemoteController:
    return RemoteController(enumerator=get_remote_enumerator())
