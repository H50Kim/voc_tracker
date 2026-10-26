"""Suggest Glean search in an existing Edge tab (reference only — not executable)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from computer_use.controllers.browser_controller import BrowserController, EdgeWindowInfo


@dataclass(frozen=True)
class GleanSearchSuggestion:
    """Reference material for the operator; never auto-run as shell/API commands."""

    query: str
    edge_handle: int
    tab_hint: str
    message: str
    reference_only: bool = True


def extract_search_query_from_goal(goal: str) -> str | None:
    lower = goal.lower()
    if "glean" not in lower and "enterprise search" not in lower:
        return None
    quoted = re.search(r'["\']([^"\']+)["\']', goal)
    if quoted:
        return quoted.group(1).strip()
    for token in ("search for", "find", "lookup", "검색"):
        if token in lower:
            idx = lower.index(token) + len(token)
            tail = goal[idx:].strip(" :\"'")
            if tail:
                return tail[:200]
    return goal.strip()[:200]


def suggest_glean_search_in_edge(
    goal: str,
    *,
    browser: BrowserController,
    preferred_handle: int | None = None,
) -> GleanSearchSuggestion | None:
    """
    Propose opening Glean in the **already attached** Edge window.

    Does not call Glean MCP or execute search — operator uses the suggestion manually.
    """
    query = extract_search_query_from_goal(goal)
    if not query:
        return None
    browser.assert_attach_only()
    windows = browser.list_edge_windows()
    if not windows:
        return None
    chosen: EdgeWindowInfo | None = None
    if preferred_handle:
        for w in windows:
            if w.handle == preferred_handle:
                chosen = w
                break
    if chosen is None:
        chosen = windows[0]
    tab = chosen.tab_hint or chosen.title
    message = (
        f"Reference: in Edge tab «{tab}» (hwnd #{chosen.handle}), "
        f"search Glean for «{query}». Treat results as read-only context — "
        "do not paste MCP/tool output into automation actions."
    )
    return GleanSearchSuggestion(
        query=query,
        edge_handle=chosen.handle,
        tab_hint=tab,
        message=message,
        reference_only=True,
    )
