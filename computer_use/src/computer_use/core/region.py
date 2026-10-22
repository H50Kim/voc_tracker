from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenRegion:
    """Axis-aligned region in screen coordinates (pixels)."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def to_mss_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    def relative_point(self, x: int, y: int) -> tuple[int, int]:
        """Map region-relative coordinates to absolute screen coordinates."""
        return self.left + x, self.top + y

    @classmethod
    def from_drag(
        cls,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> ScreenRegion:
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width == 0:
            width = 1
        if height == 0:
            height = 1
        return cls(left=left, top=top, width=width, height=height)

    def clamp_to_monitor(
        self,
        monitor_left: int,
        monitor_top: int,
        monitor_width: int,
        monitor_height: int,
    ) -> ScreenRegion:
        left = max(self.left, monitor_left)
        top = max(self.top, monitor_top)
        right = min(self.right, monitor_left + monitor_width)
        bottom = min(self.bottom, monitor_top + monitor_height)
        width = max(1, right - left)
        height = max(1, bottom - top)
        return ScreenRegion(left=left, top=top, width=width, height=height)
