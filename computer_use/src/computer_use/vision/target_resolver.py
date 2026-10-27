"""Click target resolution: semantic hint + fresh capture → screen coords (fail closed)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from computer_use.agent.types import Action, Interpretation, Observation
from computer_use.ai.uia_probe import UiaElement, list_uia_elements_for_hwnd
from computer_use.core.region import ScreenRegion
from computer_use.vision.action_score import ActionScore, score_geometry_valid, score_uia_match
from computer_use.vision.coordinate_engine import (
    CaptureMetadata,
    CoordinateSpace,
    CoordinateTransformEngine,
    ScreenPoint,
)


class ResolveOutcome(str, Enum):
    RESOLVED = "resolved"
    RECOVER = "recover"
    CONFIRM = "confirm"


@dataclass(frozen=True)
class TargetCandidate:
    target_ref: str
    bbox: ScreenRegion
    space: CoordinateSpace
    confidence: float
    source: str
    score: ActionScore = field(default_factory=ActionScore)


@dataclass(frozen=True)
class TargetResolution:
    outcome: ResolveOutcome
    screen_x: int | None = None
    screen_y: int | None = None
    confidence: float = 0.0
    reason: str = ""
    candidates: tuple[TargetCandidate, ...] = ()


@dataclass
class TargetResolverConfig:
    min_confidence: float = 0.55
    ambiguity_gap: float = 0.08
    window_handle: int | None = None
    allow_interpretation_fallback: bool = False


class TargetResolver:
    """Resolve CLICK actions using UIA + geometry; never blind LLM pixel coords."""

    def __init__(self, config: TargetResolverConfig | None = None) -> None:
        self._config = config or TargetResolverConfig()

    def resolve_click(
        self,
        action: Action,
        observation: Observation,
        *,
        interpretation: Interpretation | None,
        transform: CoordinateTransformEngine | None,
        capture_meta: CaptureMetadata | None,
    ) -> TargetResolution:
        if observation.payload is None:
            return TargetResolution(
                outcome=ResolveOutcome.RECOVER,
                reason="no_capture_payload",
            )

        try:
            img_w, img_h = observation.payload.size
        except (TypeError, ValueError):
            return TargetResolution(
                outcome=ResolveOutcome.RECOVER,
                reason="invalid_capture_size",
            )
        candidates = self._collect_candidates(
            action,
            interpretation=interpretation,
            img_w=img_w,
            img_h=img_h,
            transform=transform,
            capture_meta=capture_meta,
        )
        if not candidates:
            return TargetResolution(
                outcome=ResolveOutcome.RECOVER,
                reason="no_candidates",
            )

        ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
        best = ranked[0]
        if len(ranked) > 1:
            second = ranked[1]
            if (
                best.confidence >= self._config.min_confidence
                and second.confidence >= self._config.min_confidence
                and (best.confidence - second.confidence) < self._config.ambiguity_gap
            ):
                return TargetResolution(
                    outcome=ResolveOutcome.CONFIRM,
                    confidence=best.confidence,
                    reason="ambiguous_targets",
                    candidates=tuple(ranked[:5]),
                )

        if best.confidence < self._config.min_confidence:
            return TargetResolution(
                outcome=ResolveOutcome.CONFIRM,
                confidence=best.confidence,
                reason="below_confidence_threshold",
                candidates=tuple(ranked[:5]),
            )

        if transform is None or capture_meta is None:
            if best.space == CoordinateSpace.PHYSICAL:
                cx = best.bbox.left + best.bbox.width // 2
                cy = best.bbox.top + best.bbox.height // 2
                return TargetResolution(
                    outcome=ResolveOutcome.RESOLVED,
                    screen_x=cx,
                    screen_y=cy,
                    confidence=best.confidence,
                    candidates=(best,),
                )
            return TargetResolution(
                outcome=ResolveOutcome.RECOVER,
                reason="missing_transform_engine",
                candidates=(best,),
            )

        center = transform.bbox_center_to_physical(
            best.bbox,
            space=best.space,
            capture_meta=capture_meta,
        )
        if center is None:
            return TargetResolution(
                outcome=ResolveOutcome.RECOVER,
                reason="transform_failed",
                candidates=(best,),
            )
        return TargetResolution(
            outcome=ResolveOutcome.RESOLVED,
            screen_x=center[0],
            screen_y=center[1],
            confidence=best.confidence,
            candidates=(best,),
        )

    def _collect_candidates(
        self,
        action: Action,
        *,
        interpretation: Interpretation | None,
        img_w: int,
        img_h: int,
        transform: CoordinateTransformEngine | None,
        capture_meta: CaptureMetadata | None,
    ) -> list[TargetCandidate]:
        out: list[TargetCandidate] = []
        target_ref = action.target_id or "primary"
        hwnd = self._config.window_handle

        uia_elements = list_uia_elements_for_hwnd(hwnd)
        label_hint = ""
        if interpretation and interpretation.uia_labels:
            label_hint = interpretation.uia_labels.get(target_ref, "")
            if not label_hint and target_ref == "primary":
                label_hint = interpretation.uia_labels.get("primary", "")

        for idx, el in enumerate(uia_elements):
            ref = f"uia_{idx}"
            if target_ref not in (ref, "primary") and label_hint:
                if label_hint.split(":")[-1].lower() not in el.name.lower():
                    continue
            elif target_ref.startswith("uia_") and target_ref != ref:
                continue
            name_match = bool(label_hint and el.name.lower() in label_hint.lower())
            conf = score_uia_match(name_match=name_match, control_type=el.control_type)
            bbox = ScreenRegion(left=el.center_x - 8, top=el.center_y - 8, width=16, height=16)
            stale = False
            if capture_meta and transform and transform.capture_region:
                in_cap = (
                    transform.capture_region.left <= el.center_x < transform.capture_region.right
                    and transform.capture_region.top <= el.center_y < transform.capture_region.bottom
                )
                conf += score_geometry_valid(in_capture=in_cap, stale=stale)
            out.append(
                TargetCandidate(
                    target_ref=ref,
                    bbox=bbox,
                    space=CoordinateSpace.PHYSICAL,
                    confidence=min(conf, 1.0),
                    source="uia",
                    score=ActionScore(uia_weight=conf),
                )
            )

        if (
            action.x is not None
            and action.y is not None
        ):
            ax, ay = action.x, action.y
            if 0 <= ax < img_w and 0 <= ay < img_h:
                mapped = transform.screenshot_to_physical(ax, ay) if transform else None
                if mapped or transform is None:
                    bbox = ScreenRegion(
                        left=max(0, ax - 8), top=max(0, ay - 8), width=16, height=16
                    )
                    out.append(
                        TargetCandidate(
                            target_ref=target_ref,
                            bbox=bbox,
                            space=CoordinateSpace.SCREENSHOT,
                            confidence=0.88,
                            source="validated_screenshot_coords",
                            score=ActionScore(geometry_weight=0.88),
                        )
                    )
            elif transform and transform.capture_region:
                cap = transform.capture_region
                if cap.left <= ax < cap.right and cap.top <= ay < cap.bottom:
                    bbox = ScreenRegion(left=ax - 8, top=ay - 8, width=16, height=16)
                    out.append(
                        TargetCandidate(
                            target_ref=target_ref,
                            bbox=bbox,
                            space=CoordinateSpace.PHYSICAL,
                            confidence=0.88,
                            source="validated_physical_coords",
                            score=ActionScore(geometry_weight=0.88),
                        )
                    )

        if (
            self._config.allow_interpretation_fallback
            and interpretation
            and target_ref in interpretation.targets
        ):
            tx, ty = interpretation.targets[target_ref]
            stale = False
            if capture_meta:
                pt = ScreenPoint(tx, ty, CoordinateSpace.SCREENSHOT, capture_meta=capture_meta)
                stale = pt.is_stale(capture_meta)
            if not stale and 0 <= tx < img_w and 0 <= ty < img_h:
                bbox = ScreenRegion(left=max(0, tx - 8), top=max(0, ty - 8), width=16, height=16)
                conf = 0.42 + (0.1 if interpretation.confidence > 0.5 else 0.0)
                out.append(
                    TargetCandidate(
                        target_ref=target_ref,
                        bbox=bbox,
                        space=CoordinateSpace.SCREENSHOT,
                        confidence=conf,
                        source="interpretation_hint",
                        score=ActionScore(geometry_weight=conf),
                    )
                )

        return out


def default_target_resolver(*, window_handle: int | None = None) -> TargetResolver:
    return TargetResolver(TargetResolverConfig(window_handle=window_handle))
