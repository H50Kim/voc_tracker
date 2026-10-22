from enum import Enum


class AutomationMode(str, Enum):
    """Local desktop, existing Edge browser, or remote session (RDP/Citrix)."""

    LOCAL = "local"
    BROWSER = "browser"
    REMOTE = "remote"
