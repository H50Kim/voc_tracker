from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from computer_use.core.region import ScreenRegion


class ScreenCapture:
    """Screen capture via mss (cross-platform)."""

    def __init__(self) -> None:
        import mss

        self._mss = mss.MSS()

    def capture_screen(self, monitor_index: int = 1) -> Image.Image:
        shot = self._mss.grab(self._mss.monitors[monitor_index])
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def capture_region(self, region: ScreenRegion) -> Image.Image:
        shot = self._mss.grab(region.to_mss_dict())
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def primary_monitor_size(self) -> tuple[int, int]:
        mon = self._mss.monitors[1]
        return int(mon["width"]), int(mon["height"])

    @staticmethod
    def to_png_bytes(image: Image.Image) -> bytes:
        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
