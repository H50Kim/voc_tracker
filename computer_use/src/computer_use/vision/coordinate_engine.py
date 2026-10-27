"""Explicit coordinate spaces and transforms (deterministic engine layer)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from computer_use.core.region import ScreenRegion


class CoordinateSpace(str, Enum):
    """Named pixel spaces used across local, browser, and remote capture."""

    PHYSICAL = "physical"  # OS screen pixels (multi-monitor origin)
    LOGICAL = "logical"  # DPI-scaled logical pixels (hook for future Win32 DPI)
    WINDOW = "window"  # Relative to window outer rect top-left
    CLIENT = "client"  # Relative to window client area (same as WINDOW when no chrome)
    SCREENSHOT = "screenshot"  # Relative to captured bitmap (0,0 = top-left of clip)
    ROI = "roi"  # Alias of screenshot when clip is user ROI
    RDP_VIEWPORT = "rdp_viewport"  # Content area inside remote client chrome / letterbox


@dataclass(frozen=True)
class WindowGeometry:
    """Window outer rect on the physical desktop."""

    handle: int
    outer_rect: ScreenRegion
    dpi_scale: float = 1.0

    def geometry_hash(self) -> str:
        payload = (
            f"{self.handle}:{self.outer_rect.left},{self.outer_rect.top},"
            f"{self.outer_rect.width}x{self.outer_rect.height}:{self.dpi_scale:.4f}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class RdpViewportGeometry:
    """Remote client content viewport: inner surface minus letterbox within capture."""

    chrome_left: int = 0
    chrome_top: int = 0
    content_width: int = 0
    content_height: int = 0
    letterbox_left: int = 0
    letterbox_top: int = 0
    viewport_scale: float = 1.0

    @classmethod
    def from_window_and_inner(
        cls,
        *,
        window_rect: ScreenRegion,
        inner_relative: ScreenRegion,
        capture_region: ScreenRegion,
    ) -> RdpViewportGeometry:
        """Derive viewport mapping for RDP-style client chrome + scaled content."""
        content_screen = ScreenRegion(
            left=window_rect.left + inner_relative.left,
            top=window_rect.top + inner_relative.top,
            width=inner_relative.width,
            height=inner_relative.height,
        )
        scale_x = capture_region.width / max(1, content_screen.width)
        scale_y = capture_region.height / max(1, content_screen.height)
        viewport_scale = min(scale_x, scale_y)
        letterbox_left = 0
        letterbox_top = 0
        if capture_region.width > int(content_screen.width * viewport_scale):
            letterbox_left = (
                capture_region.width - int(content_screen.width * viewport_scale)
            ) // 2
        if capture_region.height > int(content_screen.height * viewport_scale):
            letterbox_top = (
                capture_region.height - int(content_screen.height * viewport_scale)
            ) // 2
        return cls(
            chrome_left=inner_relative.left,
            chrome_top=inner_relative.top,
            content_width=inner_relative.width,
            content_height=inner_relative.height,
            letterbox_left=letterbox_left,
            letterbox_top=letterbox_top,
            viewport_scale=viewport_scale,
        )


@dataclass(frozen=True)
class CaptureMetadata:
    """Metadata stamped on each observation capture."""

    captured_at_ms: int
    capture_region: ScreenRegion
    fingerprint: str
    window_geometry_hash: str = ""
    dpi_scale: float = 1.0
    viewport: RdpViewportGeometry | None = None
    image_width: int = 0
    image_height: int = 0

    def is_stale_vs(self, other: CaptureMetadata) -> bool:
        if self.window_geometry_hash and other.window_geometry_hash:
            if self.window_geometry_hash != other.window_geometry_hash:
                return True
        return False


@dataclass(frozen=True)
class ScreenPoint:
    """Point annotated with coordinate space and capture context."""

    x: int
    y: int
    space: CoordinateSpace
    capture_meta: CaptureMetadata | None = None

    def is_stale(self, current: CaptureMetadata) -> bool:
        if self.capture_meta is None or self.capture_meta.fingerprint == current.fingerprint:
            return False
        return self.capture_meta.is_stale_vs(current)


@dataclass
class CaptureMetadataCache:
    """Reuse capture metadata when fingerprint + geometry hash unchanged."""

    last_fingerprint: str = ""
    last_geometry_hash: str = ""
    last_meta: CaptureMetadata | None = None

    def get_or_build(
        self,
        *,
        fingerprint: str,
        geometry_hash: str,
        build: Callable[[], CaptureMetadata],
    ) -> CaptureMetadata:
        if (
            self.last_meta is not None
            and self.last_fingerprint == fingerprint
            and self.last_geometry_hash == geometry_hash
        ):
            return self.last_meta
        meta = build()
        self.last_fingerprint = fingerprint
        self.last_geometry_hash = geometry_hash
        self.last_meta = meta
        return meta


@dataclass(frozen=True)
class CoordinateTransformEngine:
    """Transform points between capture-relative and physical screen spaces."""

    window_geometry: WindowGeometry | None = None
    capture_region: ScreenRegion | None = None
    inner_relative: ScreenRegion | None = None
    viewport: RdpViewportGeometry | None = None

    @classmethod
    def from_mapper_context(
        cls,
        *,
        window_rect: ScreenRegion,
        inner_relative: ScreenRegion | None,
        capture_region: ScreenRegion | None,
        window_handle: int = 0,
        dpi_scale: float = 1.0,
    ) -> CoordinateTransformEngine:
        wg = WindowGeometry(handle=window_handle, outer_rect=window_rect, dpi_scale=dpi_scale)
        viewport = None
        if inner_relative is not None and capture_region is not None:
            viewport = RdpViewportGeometry.from_window_and_inner(
                window_rect=window_rect,
                inner_relative=inner_relative,
                capture_region=capture_region,
            )
        return cls(
            window_geometry=wg,
            capture_region=capture_region,
            inner_relative=inner_relative,
            viewport=viewport,
        )

    def screenshot_to_physical(self, sx: int, sy: int) -> tuple[int, int] | None:
        if self.capture_region is None:
            return None
        cap = self.capture_region
        if not (0 <= sx < cap.width and 0 <= sy < cap.height):
            return None
        if self.viewport is not None:
            vx = int((sx - self.viewport.letterbox_left) / max(self.viewport.viewport_scale, 1e-6))
            vy = int((sy - self.viewport.letterbox_top) / max(self.viewport.viewport_scale, 1e-6))
            if self.window_geometry is None or self.inner_relative is None:
                return cap.relative_point(sx, sy)
            wx = self.window_geometry.outer_rect.left + self.inner_relative.left + vx
            wy = self.window_geometry.outer_rect.top + self.inner_relative.top + vy
            return wx, wy
        return cap.relative_point(sx, sy)

    def physical_to_screenshot(self, px: int, py: int) -> tuple[int, int] | None:
        if self.capture_region is None:
            return None
        cap = self.capture_region
        if self.viewport is not None and self.window_geometry and self.inner_relative:
            inner_left = self.window_geometry.outer_rect.left + self.inner_relative.left
            inner_top = self.window_geometry.outer_rect.top + self.inner_relative.top
            if not (
                inner_left <= px < inner_left + self.inner_relative.width
                and inner_top <= py < inner_top + self.inner_relative.height
            ):
                if not (cap.left <= px < cap.right and cap.top <= py < cap.bottom):
                    return None
                return px - cap.left, py - cap.top
            vx = px - inner_left
            vy = py - inner_top
            sx = int(vx * self.viewport.viewport_scale) + self.viewport.letterbox_left
            sy = int(vy * self.viewport.viewport_scale) + self.viewport.letterbox_top
            if not (0 <= sx < cap.width and 0 <= sy < cap.height):
                return None
            return sx, sy
        if not (cap.left <= px < cap.right and cap.top <= py < cap.bottom):
            return None
        return px - cap.left, py - cap.top

    def transform_point(self, point: ScreenPoint, target_space: CoordinateSpace) -> ScreenPoint | None:
        if point.space == target_space:
            return point
        if target_space == CoordinateSpace.PHYSICAL and point.space in (
            CoordinateSpace.SCREENSHOT,
            CoordinateSpace.ROI,
            CoordinateSpace.RDP_VIEWPORT,
        ):
            mapped = self.screenshot_to_physical(point.x, point.y)
            if mapped is None:
                return None
            return ScreenPoint(
                x=mapped[0],
                y=mapped[1],
                space=CoordinateSpace.PHYSICAL,
                capture_meta=point.capture_meta,
            )
        if target_space in (CoordinateSpace.SCREENSHOT, CoordinateSpace.ROI) and point.space == (
            CoordinateSpace.PHYSICAL
        ):
            mapped = self.physical_to_screenshot(point.x, point.y)
            if mapped is None:
                return None
            return ScreenPoint(
                x=mapped[0],
                y=mapped[1],
                space=CoordinateSpace.SCREENSHOT,
                capture_meta=point.capture_meta,
            )
        if (
            target_space == CoordinateSpace.CLIENT
            and point.space == CoordinateSpace.PHYSICAL
            and self.window_geometry
        ):
            wx = self.window_geometry.outer_rect.left
            wy = self.window_geometry.outer_rect.top
            return ScreenPoint(
                x=point.x - wx,
                y=point.y - wy,
                space=CoordinateSpace.CLIENT,
                capture_meta=point.capture_meta,
            )
        return None

    def bbox_center_to_physical(
        self,
        bbox: ScreenRegion,
        *,
        space: CoordinateSpace,
        capture_meta: CaptureMetadata | None = None,
    ) -> tuple[int, int] | None:
        cx = bbox.left + bbox.width // 2
        cy = bbox.top + bbox.height // 2
        pt = ScreenPoint(x=cx, y=cy, space=space, capture_meta=capture_meta)
        physical = self.transform_point(pt, CoordinateSpace.PHYSICAL)
        if physical is None:
            return None
        return physical.x, physical.y


def build_capture_metadata(
    *,
    capture_region: ScreenRegion,
    fingerprint: str,
    image_width: int,
    image_height: int,
    window_geometry: WindowGeometry | None = None,
    inner_relative: ScreenRegion | None = None,
    clock_ms: int | None = None,
) -> CaptureMetadata:
    now = clock_ms if clock_ms is not None else int(time.time() * 1000)
    viewport = None
    dpi = 1.0
    geom_hash = ""
    if window_geometry is not None:
        geom_hash = window_geometry.geometry_hash()
        dpi = window_geometry.dpi_scale
        if inner_relative is not None:
            viewport = RdpViewportGeometry.from_window_and_inner(
                window_rect=window_geometry.outer_rect,
                inner_relative=inner_relative,
                capture_region=capture_region,
            )
    return CaptureMetadata(
        captured_at_ms=now,
        capture_region=capture_region,
        fingerprint=fingerprint,
        window_geometry_hash=geom_hash,
        dpi_scale=dpi,
        viewport=viewport,
        image_width=image_width,
        image_height=image_height,
    )
