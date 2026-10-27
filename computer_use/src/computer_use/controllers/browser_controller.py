"""Attach to running Microsoft Edge windows (no launch, no session harvest).

Security notes (also enforced in policy_guard):
- Never call playwright.launch(), selenium WebDriver new sessions, or CDP attach
  unless COMPUTER_USE_ALLOW_CDP=1 and explicit user opt-in.
- Do not read cookies, localStorage, session tokens, or auth headers from the browser.
"""

from __future__ import annotations

import os
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from computer_use.core.region import ScreenRegion
from computer_use.modes.browser import BrowserModePolicy, edge_attach_policy
from computer_use.policy.policy_guard import PolicyGuard, PolicyViolation

# Title heuristics for Microsoft Edge on Windows (no CDP).
_EDGE_TITLE_SUFFIX = re.compile(r"\s-\s(?:.+?\s-\s)?Microsoft\s+Edge\s*$", re.I)
_MFA_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sign\s*in", re.I),
    re.compile(r"sign-in", re.I),
    re.compile(r"login", re.I),
    re.compile(r"log\s*in", re.I),
    re.compile(r"microsoft\s+online", re.I),
    re.compile(r"accounts\.microsoft", re.I),
    re.compile(r"azure\s+ad", re.I),
    re.compile(r"multi[-\s]?factor", re.I),
    re.compile(r"verify\s+your\s+identity", re.I),
    re.compile(r"enter\s+code", re.I),
    re.compile(r"authenticator", re.I),
    re.compile(r"passkey", re.I),
    re.compile(r"security\s+info", re.I),
)
# URL-like fragments sometimes appear in window titles when copying from address bar.
_MFA_URL_FRAGMENTS: tuple[re.Pattern[str], ...] = (
    re.compile(r"login\.microsoftonline\.com", re.I),
    re.compile(r"login\.live\.com", re.I),
    re.compile(r"account\.live\.com", re.I),
    re.compile(r"aad\.", re.I),
)


def cdp_allowed_by_env() -> bool:
    return os.environ.get("COMPUTER_USE_ALLOW_CDP", "").strip() in ("1", "true", "yes")


@dataclass(frozen=True)
class EdgeWindowInfo:
    handle: int
    title: str
    tab_hint: str
    is_visible: bool = True


@dataclass(frozen=True)
class AuthPauseSignal:
    """Closed-loop should pause until the user completes interactive auth."""

    reason: str
    matched_pattern: str


def extract_tab_hint_from_title(title: str) -> str:
    """Best-effort active tab label from Edge window title (no CDP)."""
    text = title.strip()
    if not text:
        return ""
    # "Tab - Profile - Microsoft Edge" or "Tab and N more pages - Profile - Microsoft Edge"
    without_suffix = _EDGE_TITLE_SUFFIX.sub("", text).strip()
    if without_suffix:
        # Drop trailing "and N more pages"
        without_suffix = re.sub(r"\s+and\s+\d+\s+more\s+pages\s*$", "", without_suffix, flags=re.I)
        return without_suffix
    return text


def detect_auth_pause(*, title: str, tab_hint: str | None = None) -> AuthPauseSignal | None:
    """Heuristic MFA / AAD sign-in detection from visible window text only."""
    combined = f"{title} {tab_hint or ''}".strip()
    if not combined:
        return None
    for pattern in _MFA_TITLE_PATTERNS:
        if pattern.search(combined):
            return AuthPauseSignal(
                reason="Interactive sign-in or MFA detected; complete auth manually.",
                matched_pattern=pattern.pattern,
            )
    for pattern in _MFA_URL_FRAGMENTS:
        if pattern.search(combined):
            return AuthPauseSignal(
                reason="Microsoft sign-in URL pattern in window title.",
                matched_pattern=pattern.pattern,
            )
    return None


def intersect_capture_region(
    window: ScreenRegion | None,
    user: ScreenRegion | None,
) -> ScreenRegion | None:
    """Capture/input bounds = intersection of Edge client area and user-selected region."""
    if window is None and user is None:
        return None
    if window is None:
        return user
    if user is None:
        return window
    left = max(window.left, user.left)
    top = max(window.top, user.top)
    right = min(window.right, user.right)
    bottom = min(window.bottom, user.bottom)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return window
    return ScreenRegion(left=left, top=top, width=width, height=height)


class EdgeWindowEnumerator(ABC):
    @abstractmethod
    def list_edge_windows(self) -> list[EdgeWindowInfo]:
        raise NotImplementedError

    @abstractmethod
    def get_window_rect(self, handle: int) -> ScreenRegion | None:
        raise NotImplementedError

    @abstractmethod
    def get_window_title(self, handle: int) -> str:
        raise NotImplementedError

    @abstractmethod
    def focus_window(self, handle: int) -> bool:
        raise NotImplementedError


class StubEdgeWindowEnumerator(EdgeWindowEnumerator):
    """Linux / CI: fake Edge window for GUI and adapter tests."""

    def list_edge_windows(self) -> list[EdgeWindowInfo]:
        return [
            EdgeWindowInfo(
                handle=9001,
                title="Example SSO - Profile - Microsoft Edge",
                tab_hint="Example SSO",
            )
        ]

    def get_window_rect(self, handle: int) -> ScreenRegion | None:
        if handle <= 0:
            return None
        return ScreenRegion(left=100, top=80, width=1280, height=720)

    def get_window_title(self, handle: int) -> str:
        for w in self.list_edge_windows():
            if w.handle == handle:
                return w.title
        return ""

    def focus_window(self, handle: int) -> bool:
        return handle > 0


class Win32EdgeWindowEnumerator(EdgeWindowEnumerator):
    """Enumerate top-level visible Edge windows via Win32 (no new browser process)."""

    _EDGE_EXE = "msedge.exe"

    def list_edge_windows(self) -> list[EdgeWindowInfo]:
        import win32gui  # type: ignore[import-untyped]
        import win32process  # type: ignore[import-untyped]

        results: list[EdgeWindowInfo] = []

        def callback(hwnd: int, _: int) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title.strip():
                return True
            if not self._is_edge_window(hwnd, title):
                return True
            tab = extract_tab_hint_from_title(title)
            uia_tab = self._try_uia_tab_name(hwnd)
            if uia_tab:
                tab = uia_tab
            results.append(
                EdgeWindowInfo(
                    handle=int(hwnd),
                    title=title,
                    tab_hint=tab,
                    is_visible=True,
                )
            )
            return True

        win32gui.EnumWindows(callback, 0)
        results.sort(key=lambda w: w.title.lower())
        return results

    def _is_edge_window(self, hwnd: int, title: str) -> bool:
        if "microsoft edge" in title.lower():
            return True
        try:
            import win32gui  # type: ignore[import-untyped]
            import win32process  # type: ignore[import-untyped]

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = self._exe_name_for_pid(pid)
            return exe == self._EDGE_EXE
        except Exception:
            return False

    @staticmethod
    def _exe_name_for_pid(pid: int) -> str:
        import win32api  # type: ignore[import-untyped]
        import win32con  # type: ignore[import-untyped]
        import win32process  # type: ignore[import-untyped]

        access = win32con.PROCESS_QUERY_LIMITED_INFORMATION
        handle = win32api.OpenProcess(access, False, pid)
        try:
            exe_path = win32process.GetModuleFileNameEx(handle, 0)
        finally:
            win32api.CloseHandle(handle)
        return exe_path.rsplit("\\", 1)[-1].lower()

    @staticmethod
    def _try_uia_tab_name(hwnd: int) -> str | None:
        try:
            from pywinauto import Application  # type: ignore[import-untyped]

            app = Application(backend="uia").connect(handle=hwnd, timeout=1)
            window = app.window(handle=hwnd)
            for ctrl in window.descendants(control_type="TabItem"):
                name = ctrl.window_text()
                if name and name.strip():
                    return name.strip()
        except Exception:
            return None
        return None

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

    def focus_window(self, handle: int) -> bool:
        import win32con  # type: ignore[import-untyped]
        import win32gui  # type: ignore[import-untyped]

        try:
            win32gui.ShowWindow(handle, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(handle)
            return True
        except Exception:
            return False


def get_edge_enumerator() -> EdgeWindowEnumerator:
    if sys.platform == "win32":
        try:
            return Win32EdgeWindowEnumerator()
        except ImportError:
            return StubEdgeWindowEnumerator()
    return StubEdgeWindowEnumerator()


@dataclass
class BrowserController:
    """Attach-only Edge automation helper."""

    policy: BrowserModePolicy | None = None
    guard: PolicyGuard | None = None
    enumerator: EdgeWindowEnumerator | None = None
    allow_cdp_user_opt_in: bool = False

    def __post_init__(self) -> None:
        if self.policy is None:
            self.policy = edge_attach_policy()
        if self.guard is None:
            from computer_use.policy.policy_guard import DEFAULT_POLICY

            self.guard = DEFAULT_POLICY
        if self.enumerator is None:
            self.enumerator = get_edge_enumerator()

    def assert_attach_only(self) -> None:
        """Ensure attach-only policy (no new Edge process / profile)."""
        assert self.policy is not None
        if self.policy.allow_new_process_launch:
            raise PolicyViolation("BrowserModePolicy forbids new process launch.")
        if not self.policy.attach_to_existing_edge_only:
            raise PolicyViolation("Browser mode requires attach_to_existing_edge_only.")

    def assert_no_cdp_unless_allowed(self) -> None:
        assert self.guard is not None
        self.guard.check_cdp_attach(
            allowed_by_env=cdp_allowed_by_env(),
            user_opt_in=self.allow_cdp_user_opt_in,
        )

    def list_edge_windows(self) -> list[EdgeWindowInfo]:
        self.assert_attach_only()
        assert self.enumerator is not None
        return self.enumerator.list_edge_windows()

    def capture_region_for(
        self,
        *,
        window_handle: int | None,
        user_region: ScreenRegion | None,
    ) -> ScreenRegion | None:
        assert self.enumerator is not None
        window_region = (
            self.enumerator.get_window_rect(window_handle) if window_handle else None
        )
        return intersect_capture_region(window_region, user_region)

    def check_auth_for_handle(self, handle: int | None) -> AuthPauseSignal | None:
        if not handle:
            return None
        assert self.enumerator is not None
        title = self.enumerator.get_window_title(handle)
        tab = extract_tab_hint_from_title(title)
        return detect_auth_pause(title=title, tab_hint=tab)

    def focus(self, handle: int) -> bool:
        assert self.enumerator is not None
        return self.enumerator.focus_window(handle)


def block_playwright_or_selenium_launch(
    guard: PolicyGuard | None = None,
    *,
    description: str,
) -> None:
    """Policy hook: block automation APIs that spawn a new browser profile."""
    g = guard or PolicyGuard()
    g.check_browser_automation_api(description)
