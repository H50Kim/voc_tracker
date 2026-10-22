from __future__ import annotations

import hashlib
from dataclasses import dataclass

from PIL import Image, ImageChops


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    similarity: float
    message: str
    before_hash: str
    after_hash: str


class ResultValidator:
    """Compare captures to confirm UI state change (or stability)."""

    def __init__(self, *, similarity_threshold: float = 0.98) -> None:
        self.similarity_threshold = similarity_threshold

    @staticmethod
    def image_hash(image: Image.Image) -> str:
        data = image.tobytes()
        return hashlib.sha256(data).hexdigest()

    def pixel_similarity(self, a: Image.Image, b: Image.Image) -> float:
        if a.size != b.size:
            b = b.resize(a.size)
        if a.mode != "RGB":
            a = a.convert("RGB")
        if b.mode != "RGB":
            b = b.convert("RGB")
        diff = ImageChops.difference(a, b)
        hist = diff.histogram()
        # hist is 768 bins for RGB; sum weighted by distance from 0
        total_pixels = a.size[0] * a.size[1]
        if total_pixels == 0:
            return 1.0
        diff_sum = sum(i * hist[i] for i in range(256))  # approximate on R channel slice
        max_diff = 255 * total_pixels
        return 1.0 - (diff_sum / max_diff)

    def validate_unchanged(self, before: Image.Image, after: Image.Image) -> ValidationResult:
        sim = self.pixel_similarity(before, after)
        passed = sim >= self.similarity_threshold
        return ValidationResult(
            passed=passed,
            similarity=sim,
            message="Screens match (stable)" if passed else "Unexpected visual change",
            before_hash=self.image_hash(before),
            after_hash=self.image_hash(after),
        )

    def validate_changed(
        self,
        before: Image.Image,
        after: Image.Image,
        *,
        change_threshold: float = 0.95,
    ) -> ValidationResult:
        sim = self.pixel_similarity(before, after)
        passed = sim < change_threshold
        return ValidationResult(
            passed=passed,
            similarity=sim,
            message="Visual change detected" if passed else "No significant change",
            before_hash=self.image_hash(before),
            after_hash=self.image_hash(after),
        )
