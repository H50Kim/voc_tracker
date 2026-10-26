"""Mask sensitive substrings before writing to GUI logs."""

from __future__ import annotations

import re

_SENSITIVE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|cookie|authorization)\s*[:=]\s*\S+",
    re.I,
)


def mask_log_line(text: str) -> str:
    return _SENSITIVE.sub(r"\1=***", text)
