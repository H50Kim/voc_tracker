"""Pixel-level screen difference helpers for closed-loop verify."""

from __future__ import annotations

from PIL import Image

from computer_use.core.validator import ResultValidator


def screen_diff_ratio(before: Image.Image, after: Image.Image) -> float:
    """Return dissimilarity in [0, 1]; 0 = identical, 1 = maximally different."""
    validator = ResultValidator()
    similarity = validator.pixel_similarity(before, after)
    return max(0.0, min(1.0, 1.0 - similarity))


def screens_unchanged(
    before: Image.Image,
    after: Image.Image,
    *,
    similarity_threshold: float = 0.98,
) -> bool:
    """True when frames are visually stable (no meaningful change)."""
    validator = ResultValidator(similarity_threshold=similarity_threshold)
    return validator.validate_unchanged(before, after).passed
