"""Browser (Edge) mode — Phase 2. No launch() or CDP in Phase 1."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserModePolicy:
    """Attach-only policy for existing Edge windows."""

    attach_to_existing_edge_only: bool = True
    allow_new_process_launch: bool = False
    allow_cdp: bool = False


def edge_attach_policy() -> BrowserModePolicy:
    return BrowserModePolicy()
