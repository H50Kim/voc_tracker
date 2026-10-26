"""Extended validation hooks: screen change, text hints, file existence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from computer_use.core.validator import ResultValidator, ValidationResult


@dataclass(frozen=True)
class HookValidationResult:
    passed: bool
    hook: str
    message: str
    detail: ValidationResult | None = None


class ExtendedResultValidator:
    """Wraps core pixel validator with optional non-pixel hooks."""

    def __init__(self, *, core: ResultValidator | None = None) -> None:
        self.core = core or ResultValidator()

    def validate_screen_change(
        self,
        before: Image.Image,
        after: Image.Image,
        *,
        change_threshold: float = 0.95,
    ) -> HookValidationResult:
        detail = self.core.validate_changed(before, after, change_threshold=change_threshold)
        return HookValidationResult(
            passed=detail.passed,
            hook="screen_change",
            message=detail.message,
            detail=detail,
        )

    def validate_screen_stable(
        self,
        before: Image.Image,
        after: Image.Image,
    ) -> HookValidationResult:
        detail = self.core.validate_unchanged(before, after)
        return HookValidationResult(
            passed=detail.passed,
            hook="screen_stable",
            message=detail.message,
            detail=detail,
        )

    def validate_text_present(
        self,
        *,
        haystack: str,
        needle: str,
        case_insensitive: bool = True,
    ) -> HookValidationResult:
        if not needle.strip():
            return HookValidationResult(
                passed=False,
                hook="text_present",
                message="Empty needle text",
            )
        if case_insensitive:
            passed = needle.lower() in haystack.lower()
        else:
            passed = needle in haystack
        return HookValidationResult(
            passed=passed,
            hook="text_present",
            message="Text found" if passed else "Text not found",
        )

    def validate_file_exists(self, path: str | Path) -> HookValidationResult:
        p = Path(path).expanduser()
        passed = p.is_file()
        return HookValidationResult(
            passed=passed,
            hook="file_exists",
            message=f"File exists: {p.name}" if passed else f"Missing file: {p.name}",
        )
