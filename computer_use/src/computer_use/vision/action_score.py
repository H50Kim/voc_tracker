"""Deterministic scoring hooks for resolved targets and verify confidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionScore:
    """Aggregate score for a click candidate (higher is better)."""

    uia_weight: float = 0.0
    template_weight: float = 0.0
    geometry_weight: float = 0.0

    @property
    def total(self) -> float:
        return self.uia_weight + self.template_weight + self.geometry_weight


def score_uia_match(*, name_match: bool, control_type: str) -> float:
    base = 0.75 if name_match else 0.45
    if control_type.lower() in ("button", "hyperlink", "menuitem"):
        base += 0.1
    return min(base, 1.0)


def score_geometry_valid(*, in_capture: bool, stale: bool) -> float:
    if stale:
        return 0.0
    return 0.2 if in_capture else 0.0
