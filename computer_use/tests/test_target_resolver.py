"""Target resolver unit tests (fail-closed ambiguity, screenshot coords)."""

from PIL import Image

from computer_use.agent.types import Action, ActionKind, Interpretation, Observation
from computer_use.core.region import ScreenRegion
from computer_use.vision.coordinate_engine import (
    CoordinateTransformEngine,
    build_capture_metadata,
)
from computer_use.vision.target_resolver import ResolveOutcome, TargetResolver, TargetResolverConfig


def _obs(w: int = 400, h: int = 300) -> Observation:
    img = Image.new("RGB", (w, h))
    cap = ScreenRegion(left=50, top=40, width=w, height=h)
    meta = build_capture_metadata(
        capture_region=cap,
        fingerprint="fp",
        image_width=w,
        image_height=h,
    )
    return Observation(frame_id="test", payload=img, capture_meta=meta)


def test_resolver_accepts_validated_screenshot_coords():
    resolver = TargetResolver(TargetResolverConfig(window_handle=None))
    action = Action(
        kind=ActionKind.CLICK,
        semantic_operation_key="t:1",
        description="click",
        target_id="primary",
        x=50,
        y=60,
    )
    obs = _obs()
    transform = CoordinateTransformEngine(capture_region=obs.capture_meta.capture_region)
    res = resolver.resolve_click(
        action,
        obs,
        interpretation=None,
        transform=transform,
        capture_meta=obs.capture_meta,
    )
    assert res.outcome == ResolveOutcome.RESOLVED
    assert res.screen_x == 100
    assert res.screen_y == 100


def test_resolver_fail_closed_without_candidates():
    resolver = TargetResolver(TargetResolverConfig(window_handle=None))
    action = Action(
        kind=ActionKind.CLICK,
        semantic_operation_key="t:2",
        description="click",
        target_id="missing",
        x=None,
        y=None,
    )
    obs = _obs()
    transform = CoordinateTransformEngine(capture_region=obs.capture_meta.capture_region)
    res = resolver.resolve_click(
        action,
        obs,
        interpretation=Interpretation(summary="s", targets={}),
        transform=transform,
        capture_meta=obs.capture_meta,
    )
    assert res.outcome == ResolveOutcome.RECOVER


def test_resolver_ambiguous_low_confidence_confirm():
    resolver = TargetResolver(TargetResolverConfig(min_confidence=0.9, window_handle=None))
    action = Action(
        kind=ActionKind.CLICK,
        semantic_operation_key="t:3",
        description="click",
        target_id="primary",
        x=10,
        y=10,
    )
    obs = _obs()
    transform = CoordinateTransformEngine(capture_region=obs.capture_meta.capture_region)
    res = resolver.resolve_click(
        action,
        obs,
        interpretation=None,
        transform=transform,
        capture_meta=obs.capture_meta,
    )
    assert res.outcome == ResolveOutcome.CONFIRM
