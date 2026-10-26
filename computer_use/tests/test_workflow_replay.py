from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image

from computer_use.core.region import ScreenRegion
from computer_use.core.validator import ResultValidator
from computer_use.workflow.replay import WorkflowReplayer
from computer_use.workflow.types import (
    ElementFeatures,
    ScreenFingerprint,
    WorkflowDocument,
    WorkflowStep,
)


class _FixedCapture:
    def __init__(self, image: Image.Image) -> None:
        self._image = image

    def capture_region(self, region: ScreenRegion) -> Image.Image:
        return self._image.copy()

    def capture_screen(self) -> Image.Image:
        return self._image.copy()

    def primary_monitor_size(self) -> tuple[int, int]:
        return self._image.size


def _solid(size: tuple[int, int], color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", size, color)


def test_replay_dry_run_click_with_matching_fingerprint():
    img = _solid((100, 80), (40, 80, 120))
    validator = ResultValidator()
    region_hash = validator.image_hash(img)
    fp = ScreenFingerprint(0, 0, 100, 80, region_hash=region_hash)
    step = WorkflowStep(
        kind="click",
        fingerprint=fp,
        element=ElementFeatures(rel_x=0.25, rel_y=0.5),
    )
    doc = WorkflowDocument(steps=[step])
    replayer = WorkflowReplayer(
        capture=_FixedCapture(img),
        dry_run=True,
        validator=validator,
    )
    result = replayer.replay(doc)
    assert result.success
    assert "Dry-run click" in result.outcomes[0].message


def test_replay_fails_on_fingerprint_mismatch():
    before = _solid((50, 50), (10, 10, 10))
    after = _solid((50, 50), (200, 10, 10))
    validator = ResultValidator()
    fp = ScreenFingerprint(
        0, 0, 50, 50, region_hash=validator.image_hash(before)
    )
    step = WorkflowStep(
        kind="click",
        fingerprint=fp,
        element=ElementFeatures(rel_x=0.5, rel_y=0.5),
    )
    replayer = WorkflowReplayer(
        capture=_FixedCapture(after),
        dry_run=True,
        validator=validator,
    )
    result = replayer.replay(WorkflowDocument(steps=[step]))
    assert not result.success
    assert "Verify failed" in result.outcomes[0].message


def test_resolve_click_uses_template_patch():
    haystack = _solid((60, 60), (30, 30, 30))
    needle = _solid((8, 8), (250, 250, 250))
    haystack.paste(needle, (20, 25))
    buf = BytesIO()
    needle.save(buf, format="PNG")
    patch_b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    validator = ResultValidator()
    fp = ScreenFingerprint(
        0, 0, 60, 60, region_hash=validator.image_hash(haystack)
    )
    step = WorkflowStep(
        kind="click",
        fingerprint=fp,
        element=ElementFeatures(
            rel_x=0.1,
            rel_y=0.1,
            local_patch_b64=patch_b64,
            patch_width=8,
            patch_height=8,
        ),
    )
    replayer = WorkflowReplayer(
        capture=_FixedCapture(haystack),
        dry_run=True,
        validator=validator,
    )
    point = replayer.resolve_click(step)
    assert point is not None
    x, y = point
    assert 20 <= x <= 28
    assert 25 <= y <= 33


def test_glean_helper_parse_reference_only():
    from computer_use.workflow.glean_helper import GleanHelper

    helper = GleanHelper()
    html = '<a href="https://example.com/doc">Policy guide</a><p>Summary text</p>'
    results = helper.parse_reference_results(html)
    assert len(results) == 1
    assert results[0].url.startswith("https://")
    assert "Policy" in results[0].title
