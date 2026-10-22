"""Block dangerous automation patterns (no auth bypass, no cookie harvest)."""

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
        }
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

    def filter_window_titles(self, titles: Iterable[str]) -> list[str]:
        return [t for t in titles if t.strip()]


DEFAULT_POLICY = PolicyGuard()
