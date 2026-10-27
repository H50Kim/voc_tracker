"""Edge attach controller — Linux fakes (no Win32)."""

from __future__ import annotations

import pytest

from computer_use.controllers.browser_controller import (
    AuthPauseSignal,
    BrowserController,
    StubEdgeWindowEnumerator,
    cdp_allowed_by_env,
    detect_auth_pause,
    extract_tab_hint_from_title,
    intersect_capture_region,
)
from computer_use.core.region import ScreenRegion
from computer_use.policy.policy_guard import PolicyGuard, PolicyViolation


def test_extract_tab_hint_from_edge_title():
    title = "Contoso Portal - Work - Microsoft Edge"
    assert extract_tab_hint_from_title(title) == "Contoso Portal"


def test_extract_tab_hint_multi_tab_suffix():
    title = "Inbox and 2 more pages - Profile - Microsoft Edge"
    assert extract_tab_hint_from_title(title) == "Inbox"


def test_detect_auth_pause_sign_in_title():
    signal = detect_auth_pause(title="Sign in to your account - Microsoft Edge", tab_hint="Sign in")
    assert isinstance(signal, AuthPauseSignal)
    assert "sign-in" in signal.reason.lower() or "Interactive" in signal.reason


def test_detect_auth_pause_clean_title():
    assert detect_auth_pause(title="News - Microsoft Edge", tab_hint="News") is None


def test_intersect_capture_region_clamps_to_window():
    window = ScreenRegion(100, 100, 800, 600)
    user = ScreenRegion(500, 200, 400, 400)
    merged = intersect_capture_region(window, user)
    assert merged is not None
    assert merged.left == 500
    assert merged.top == 200
    assert merged.width == 400
    assert merged.height == 400


def test_stub_edge_enumerator_lists_fake_edge():
    enum = StubEdgeWindowEnumerator()
    wins = enum.list_edge_windows()
    assert len(wins) == 1
    assert wins[0].handle == 9001
    assert "Microsoft Edge" in wins[0].title


def test_browser_controller_capture_region_intersection():
    ctrl = BrowserController(enumerator=StubEdgeWindowEnumerator())
    region = ctrl.capture_region_for(
        window_handle=9001,
        user_region=ScreenRegion(200, 100, 300, 300),
    )
    assert region is not None
    assert region.left >= 100


def test_policy_blocks_playwright_launch():
    guard = PolicyGuard()
    with pytest.raises(PolicyViolation):
        guard.check_browser_automation_api("playwright.launch(channel='msedge')")


def test_policy_blocks_session_harvest():
    guard = PolicyGuard()
    with pytest.raises(PolicyViolation):
        guard.check_session_harvest("return localStorage.getItem('token')")


def test_policy_blocks_cdp_without_env(monkeypatch):
    monkeypatch.delenv("COMPUTER_USE_ALLOW_CDP", raising=False)
    guard = PolicyGuard()
    with pytest.raises(PolicyViolation):
        guard.check_cdp_attach(allowed_by_env=cdp_allowed_by_env(), user_opt_in=True)


def test_policy_allows_cdp_with_env_and_opt_in(monkeypatch):
    monkeypatch.setenv("COMPUTER_USE_ALLOW_CDP", "1")
    guard = PolicyGuard()
    guard.check_cdp_attach(allowed_by_env=cdp_allowed_by_env(), user_opt_in=True)


def test_auth_pause_on_stub_sign_in_window():
    ctrl = BrowserController(enumerator=StubEdgeWindowEnumerator())
    # Stub title is not auth — inject via fake enumerator subclass
    class SignInStub(StubEdgeWindowEnumerator):
        def get_window_title(self, handle: int) -> str:
            return "Sign in - Microsoft Edge"

    ctrl = BrowserController(enumerator=SignInStub())
    signal = ctrl.check_auth_for_handle(9001)
    assert signal is not None
