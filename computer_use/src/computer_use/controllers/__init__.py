from computer_use.controllers.browser_controller import (
    AuthPauseSignal,
    BrowserController,
    EdgeWindowInfo,
    cdp_allowed_by_env,
    detect_auth_pause,
    extract_tab_hint_from_title,
    intersect_capture_region,
)

__all__ = [
    "AuthPauseSignal",
    "BrowserController",
    "EdgeWindowInfo",
    "cdp_allowed_by_env",
    "detect_auth_pause",
    "extract_tab_hint_from_title",
    "intersect_capture_region",
]
