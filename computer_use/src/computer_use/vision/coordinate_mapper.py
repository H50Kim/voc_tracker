"""Map screen coordinates ↔ remote client surface (capture-relative) coords."""

from __future__ import annotations

from dataclasses import dataclass

from computer_use.controllers.browser_controller import intersect_capture_region
from computer_use.core.region import ScreenRegion
from computer_use.vision.coordinate_engine import (
    CoordinateTransformEngine,
    WindowGeometry,
)


@dataclass(frozen=True)
class RemoteSurfaceBinding:
    """Window rect plus inner region relative to window top-left."""

    window_handle: int
    inner_relative: ScreenRegion

    def inner_on_screen(self, window_rect: ScreenRegion) -> ScreenRegion:
        return ScreenRegion(
            left=window_rect.left + self.inner_relative.left,
            top=window_rect.top + self.inner_relative.top,
            width=self.inner_relative.width,
            height=self.inner_relative.height,
        )


@dataclass(frozen=True)
class CoordinateMapper:
    """Maps between screen pixels and coordinates within the capture clip."""

    window_rect: ScreenRegion
    inner_relative: ScreenRegion
    user_screen_region: ScreenRegion | None = None

    @classmethod
    def from_binding(
        cls,
        *,
        window_rect: ScreenRegion,
        binding: RemoteSurfaceBinding,
        user_screen_region: ScreenRegion | None = None,
    ) -> CoordinateMapper:
        return cls(
            window_rect=window_rect,
            inner_relative=binding.inner_relative,
            user_screen_region=user_screen_region,
        )

    def capture_region(self) -> ScreenRegion | None:
        inner_screen = ScreenRegion(
            left=self.window_rect.left + self.inner_relative.left,
            top=self.window_rect.top + self.inner_relative.top,
            width=self.inner_relative.width,
            height=self.inner_relative.height,
        )
        return intersect_capture_region(inner_screen, self.user_screen_region)

    def screen_to_capture_relative(self, screen_x: int, screen_y: int) -> tuple[int, int] | None:
        cap = self.capture_region()
        if cap is None:
            return None
        if not (cap.left <= screen_x < cap.right and cap.top <= screen_y < cap.bottom):
            return None
        return screen_x - cap.left, screen_y - cap.top

    def capture_relative_to_screen(self, rel_x: int, rel_y: int) -> tuple[int, int] | None:
        cap = self.capture_region()
        if cap is None:
            return None
        if not (0 <= rel_x < cap.width and 0 <= rel_y < cap.height):
            return None
        return cap.relative_point(rel_x, rel_y)

    def screen_to_client_relative(self, screen_x: int, screen_y: int) -> tuple[int, int] | None:
        wx, wy = self.window_rect.left, self.window_rect.top
        cx, cy = screen_x - wx, screen_y - wy
        if not (
            0 <= cx < self.window_rect.width and 0 <= cy < self.window_rect.height
        ):
            return None
        return cx, cy

    def client_relative_to_screen(self, client_x: int, client_y: int) -> tuple[int, int]:
        return self.window_rect.left + client_x, self.window_rect.top + client_y

    def refresh_window_rect(self, new_rect: ScreenRegion) -> CoordinateMapper:
        return CoordinateMapper(
            window_rect=new_rect,
            inner_relative=self.inner_relative,
            user_screen_region=self.user_screen_region,
        )

    def transform_engine(self, *, window_handle: int = 0, dpi_scale: float = 1.0) -> CoordinateTransformEngine:
        return CoordinateTransformEngine.from_mapper_context(
            window_rect=self.window_rect,
            inner_relative=self.inner_relative,
            capture_region=self.capture_region(),
            window_handle=window_handle,
            dpi_scale=dpi_scale,
        )

    def window_geometry(self, *, window_handle: int = 0, dpi_scale: float = 1.0) -> WindowGeometry:
        return WindowGeometry(
            handle=window_handle,
            outer_rect=self.window_rect,
            dpi_scale=dpi_scale,
        )


def screen_drag_to_inner_relative(
    window_rect: ScreenRegion,
    user_screen_region: ScreenRegion,
) -> ScreenRegion | None:
    """Convert GUI drag (screen coords) to inner region relative to window."""
    inter = intersect_capture_region(window_rect, user_screen_region)
    if inter is None:
        return None
    rel_left = inter.left - window_rect.left
    rel_top = inter.top - window_rect.top
    if rel_left < 0 or rel_top < 0:
        return None
    return ScreenRegion(
        left=rel_left,
        top=rel_top,
        width=inter.width,
        height=inter.height,
    )
