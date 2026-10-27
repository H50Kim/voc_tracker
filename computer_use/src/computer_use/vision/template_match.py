"""Naive template matching for verify hooks (no OpenCV dependency)."""

from __future__ import annotations

from PIL import Image


def template_match(
    haystack: Image.Image,
    needle: Image.Image,
    *,
    similarity_threshold: float = 0.92,
) -> tuple[int, int] | None:
    """Find top-left of needle in haystack; returns None if no match above threshold."""
    if needle.width > haystack.width or needle.height > haystack.height:
        return None
    if haystack.mode != "RGB":
        haystack = haystack.convert("RGB")
    if needle.mode != "RGB":
        needle = needle.convert("RGB")

    nw, nh = needle.size
    hw, hh = haystack.size
    needle_pixels = list(needle.getdata())

    best_score = -1.0
    best_xy: tuple[int, int] | None = None

    for y in range(hh - nh + 1):
        for x in range(hw - nw + 1):
            patch = haystack.crop((x, y, x + nw, y + nh))
            patch_pixels = list(patch.getdata())
            if len(patch_pixels) != len(needle_pixels):
                continue
            matches = sum(
                1
                for a, b in zip(patch_pixels, needle_pixels, strict=True)
                if abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]) < 30
            )
            score = matches / len(needle_pixels)
            if score > best_score:
                best_score = score
                best_xy = (x, y)

    if best_xy is None or best_score < similarity_threshold:
        return None
    return best_xy
