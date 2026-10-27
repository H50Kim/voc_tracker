"""Unit tests for coordinate transform engine (synthetic geometry, no Windows)."""

from computer_use.core.region import ScreenRegion
from computer_use.vision.coordinate_engine import (
    CaptureMetadata,
    CaptureMetadataCache,
    CoordinateSpace,
    CoordinateTransformEngine,
    RdpViewportGeometry,
    ScreenPoint,
    WindowGeometry,
    build_capture_metadata,
)


def test_screenshot_physical_round_trip_local():
    cap = ScreenRegion(left=100, top=50, width=800, height=600)
    engine = CoordinateTransformEngine(capture_region=cap)
    sx, sy = 120, 80
    physical = engine.screenshot_to_physical(sx, sy)
    assert physical == (220, 130)
    back = engine.physical_to_screenshot(*physical)
    assert back == (sx, sy)


def test_stale_point_when_geometry_hash_changes():
    cap = ScreenRegion(left=0, top=0, width=640, height=480)
    meta_a = build_capture_metadata(
        capture_region=cap,
        fingerprint="fp-a",
        image_width=640,
        image_height=480,
        window_geometry=WindowGeometry(handle=1, outer_rect=ScreenRegion(0, 0, 1024, 768)),
    )
    meta_b = build_capture_metadata(
        capture_region=cap,
        fingerprint="fp-b",
        image_width=640,
        image_height=480,
        window_geometry=WindowGeometry(
            handle=1,
            outer_rect=ScreenRegion(10, 10, 1024, 768),
        ),
    )
    pt = ScreenPoint(10, 10, CoordinateSpace.SCREENSHOT, capture_meta=meta_a)
    assert pt.is_stale(meta_b) is True
    assert meta_a.is_stale_vs(meta_b) is True


def test_rdp_viewport_letterbox_mapping():
    window = ScreenRegion(left=50, top=40, width=1024, height=768)
    inner = ScreenRegion(left=0, top=0, width=400, height=300)
    cap = ScreenRegion(left=50, top=40, width=400, height=300)
    viewport = RdpViewportGeometry.from_window_and_inner(
        window_rect=window,
        inner_relative=inner,
        capture_region=cap,
    )
    engine = CoordinateTransformEngine(
        window_geometry=WindowGeometry(handle=9100, outer_rect=window),
        capture_region=cap,
        inner_relative=inner,
        viewport=viewport,
    )
    physical = engine.screenshot_to_physical(50, 60)
    assert physical == (100, 100)
    shot = engine.physical_to_screenshot(100, 100)
    assert shot == (50, 60)


def test_capture_metadata_cache_reuses_entry():
    cache = CaptureMetadataCache()
    cap = ScreenRegion(left=0, top=0, width=10, height=10)
    built = 0

    def build():
        nonlocal built
        built += 1
        return build_capture_metadata(
            capture_region=cap,
            fingerprint="same",
            image_width=10,
            image_height=10,
        )

    m1 = cache.get_or_build(fingerprint="same", geometry_hash="g1", build=build)
    m2 = cache.get_or_build(fingerprint="same", geometry_hash="g1", build=build)
    assert built == 1
    assert m1.captured_at_ms == m2.captured_at_ms
    cache.get_or_build(fingerprint="other", geometry_hash="g1", build=build)
    assert built == 2


def test_coordinate_mapper_transform_engine_integration():
    from computer_use.vision.coordinate_mapper import CoordinateMapper

    mapper = CoordinateMapper(
        window_rect=ScreenRegion(50, 40, 1024, 768),
        inner_relative=ScreenRegion(0, 0, 400, 300),
        user_screen_region=None,
    )
    engine = mapper.transform_engine(window_handle=9100)
    cap = mapper.capture_region()
    assert cap is not None
    assert engine.screenshot_to_physical(10, 20) == (
        cap.left + 10,
        cap.top + 20,
    )
