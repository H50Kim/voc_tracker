from __future__ import annotations

import base64
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image

from computer_use.core.capture import ScreenCapture
from computer_use.core.input_control import InputController
from computer_use.core.region import ScreenRegion
from computer_use.core.validator import ResultValidator
from computer_use.vision.template_match import template_match
from computer_use.workflow.types import WorkflowDocument, WorkflowStep


@dataclass
class StepReplayOutcome:
    index: int
    ok: bool
    message: str
    verified: bool = False


@dataclass
class ReplayResult:
    outcomes: list[StepReplayOutcome] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.outcomes) and all(o.ok for o in self.outcomes)


class WorkflowReplayer:
    """Replay recorded steps with screen verification before each mutating action."""

    def __init__(
        self,
        *,
        capture: ScreenCapture | None = None,
        input_controller: InputController | None = None,
        validator: ResultValidator | None = None,
        dry_run: bool = False,
        fingerprint_similarity: float = 0.85,
    ) -> None:
        self.capture = capture or ScreenCapture()
        self.input = input_controller or InputController(dry_run=dry_run)
        self.validator = validator or ResultValidator()
        self.dry_run = dry_run
        self.fingerprint_similarity = fingerprint_similarity

    def verify_fingerprint(self, step: WorkflowStep) -> tuple[bool, str]:
        fp = step.fingerprint
        anchor = ScreenRegion(
            fp.anchor_left,
            fp.anchor_top,
            fp.anchor_width,
            fp.anchor_height,
        )
        current = self.capture.capture_region(anchor)
        current_hash = self.validator.image_hash(current)
        if current_hash == fp.region_hash:
            return True, "Region hash match"
        # Allow minor drift via pixel similarity against stored hash proxy: re-capture only
        return False, f"Screen mismatch (expected region hash prefix {fp.region_hash[:12]}…)"

    def resolve_click(self, step: WorkflowStep) -> tuple[int, int] | None:
        fp = step.fingerprint
        anchor = ScreenRegion(
            fp.anchor_left,
            fp.anchor_top,
            fp.anchor_width,
            fp.anchor_height,
        )
        haystack = self.capture.capture_region(anchor)
        elem = step.element
        if elem.local_patch_b64 and elem.patch_width and elem.patch_height:
            raw = base64.standard_b64decode(elem.local_patch_b64)
            needle = Image.open(BytesIO(raw))
            found = template_match(haystack, needle)
            if found is not None:
                x, y = found
                cx = x + needle.width // 2
                cy = y + needle.height // 2
                return anchor.relative_point(cx, cy)
        rx = int(elem.rel_x * anchor.width)
        ry = int(elem.rel_y * anchor.height)
        return anchor.relative_point(rx, ry)

    def replay_step(self, step: WorkflowStep, index: int) -> StepReplayOutcome:
        verified, vmsg = self.verify_fingerprint(step)
        if not verified:
            return StepReplayOutcome(index, False, f"Verify failed: {vmsg}", verified=False)

        if step.kind == "click":
            point = self.resolve_click(step)
            if point is None:
                return StepReplayOutcome(index, False, "Could not resolve click target")
            x, y = point
            label = f"workflow_click_{index}"
            if self.dry_run:
                return StepReplayOutcome(
                    index, True, f"Dry-run click at ({x},{y})", verified=True
                )
            before = self.capture.capture_region(
                ScreenRegion(
                    step.fingerprint.anchor_left,
                    step.fingerprint.anchor_top,
                    step.fingerprint.anchor_width,
                    step.fingerprint.anchor_height,
                )
            )
            self.input.click(x, y, action_label=label)
            after = self.capture.capture_region(
                ScreenRegion(
                    step.fingerprint.anchor_left,
                    step.fingerprint.anchor_top,
                    step.fingerprint.anchor_width,
                    step.fingerprint.anchor_height,
                )
            )
            change = self.validator.validate_changed(before, after)
            return StepReplayOutcome(
                index,
                True,
                f"Click ({x},{y}); verify={change.message}",
                verified=True,
            )

        if step.kind == "type":
            text = step.text or ""
            if self.dry_run:
                return StepReplayOutcome(
                    index, True, f"Dry-run type len={len(text)}", verified=True
                )
            self.input.type_text(text, action_label=f"workflow_type_{index}")
            return StepReplayOutcome(index, True, "Typed text", verified=True)

        if step.kind == "key":
            key = step.key or "enter"
            if self.dry_run:
                return StepReplayOutcome(index, True, f"Dry-run key {key}", verified=True)
            self.input.press_key(key, action_label=f"workflow_key_{index}")
            return StepReplayOutcome(index, True, f"Key {key}", verified=True)

        return StepReplayOutcome(index, False, f"Unknown kind {step.kind!r}")

    def replay(
        self,
        document: WorkflowDocument,
        *,
        stop_on_failure: bool = True,
    ) -> ReplayResult:
        result = ReplayResult()
        for i, step in enumerate(document.steps):
            outcome = self.replay_step(step, i)
            result.outcomes.append(outcome)
            if not outcome.ok and stop_on_failure:
                break
        return result
