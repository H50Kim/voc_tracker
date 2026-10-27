"""Browser (Edge) mode — attach to running windows only (Phase 2)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserModePolicy:
    """Attach-only policy for existing Edge windows."""

    attach_to_existing_edge_only: bool = True
    allow_new_process_launch: bool = False
    allow_cdp: bool = False


def edge_attach_policy() -> BrowserModePolicy:
    return BrowserModePolicy()


def default_browser_controller(*, allow_cdp_user_opt_in: bool = False):
    """Shared attach-only controller (lazy import avoids modes ↔ controllers cycle)."""
    from computer_use.controllers.browser_controller import BrowserController, get_edge_enumerator

    return BrowserController(
        policy=edge_attach_policy(),
        enumerator=get_edge_enumerator(),
        allow_cdp_user_opt_in=allow_cdp_user_opt_in,
    )
