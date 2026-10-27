"""Block dangerous automation patterns (no auth bypass, no cookie/session harvest).

Browser attach mode must not spawn Edge via Playwright/Selenium or export cookies/tokens.
CDP is blocked unless COMPUTER_USE_ALLOW_CDP=1 and explicit user opt-in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


class PolicyViolation(Exception):
    """Raised when an action violates automation policy."""


@dataclass(frozen=True)
class PolicyGuard:
    forbidden_action_patterns: tuple[re.Pattern[str], ...] = (
        re.compile(r"cookie", re.I),
        re.compile(r"localstorage", re.I),
        re.compile(r"sessionstorage", re.I),
        re.compile(r"document\.cookie", re.I),
        re.compile(r"bypass.*auth", re.I),
        re.compile(r"cdp", re.I),
        re.compile(r"chrome\.devtools", re.I),
    )
    forbidden_key_sequences: frozenset[str] = frozenset(
        {
            "extract_cookies",
            "dump_storage",
            "disable_mfa",
            "export_session",
            "read_localstorage",
        }
    )
    browser_launch_api_patterns: tuple[re.Pattern[str], ...] = (
        re.compile(r"playwright\.(?:sync_api|async_api)\.[\w.]+\.launch", re.I),
        re.compile(r"playwright\.launch\s*\(", re.I),
        re.compile(r"selenium\.webdriver", re.I),
        re.compile(r"webdriver\.(?:Edge|Chrome)\s*\(", re.I),
        re.compile(r"msedgedriver", re.I),
        re.compile(r"chromedriver", re.I),
    )
    session_harvest_patterns: tuple[re.Pattern[str], ...] = (
        re.compile(r"document\.cookie", re.I),
        re.compile(r"navigator\.cookieEnabled", re.I),
        re.compile(r"localStorage\.getItem", re.I),
        re.compile(r"sessionStorage\.getItem", re.I),
        re.compile(r"Network\.getCookies", re.I),
        re.compile(r"Storage\.getCookies", re.I),
        re.compile(r"export.*session", re.I),
        re.compile(r"harvest.*token", re.I),
    )

    def check_text_action(self, description: str) -> None:
        for pattern in self.forbidden_action_patterns:
            if pattern.search(description):
                raise PolicyViolation(
                    f"Action blocked by policy_guard: {description!r}"
                )

    def check_key_action(self, action_id: str) -> None:
        if action_id in self.forbidden_key_sequences:
            raise PolicyViolation(f"Action id blocked: {action_id!r}")

    def check_launch_browser(self, *, new_process: bool) -> None:
        if new_process:
            raise PolicyViolation(
                "Launching a new browser process is not allowed; attach to existing Edge."
            )

    def check_browser_automation_api(self, description: str) -> None:
        for pattern in self.browser_launch_api_patterns:
            if pattern.search(description):
                raise PolicyViolation(
                    f"Browser launch API blocked (attach-only): {description!r}"
                )
        self.check_text_action(description)

    def check_session_harvest(self, description: str) -> None:
        """Reject cookie/localStorage/session token extraction (no auth bypass)."""
        for pattern in self.session_harvest_patterns:
            if pattern.search(description):
                raise PolicyViolation(
                    f"Session/cookie harvest blocked: {description!r}"
                )
        self.check_text_action(description)

    def check_cdp_attach(self, *, allowed_by_env: bool, user_opt_in: bool) -> None:
        if allowed_by_env and user_opt_in:
            return
        raise PolicyViolation(
            "CDP attach is disabled; set COMPUTER_USE_ALLOW_CDP=1 and opt in explicitly."
        )

    def filter_window_titles(self, titles: Iterable[str]) -> list[str]:
        return [t for t in titles if t.strip()]


DEFAULT_POLICY = PolicyGuard()
