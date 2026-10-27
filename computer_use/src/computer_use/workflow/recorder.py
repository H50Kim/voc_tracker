from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Callable

from computer_use.core.capture import ScreenCapture
from computer_use.core.region import ScreenRegion
from computer_use.core.validator import ResultValidator
from computer_use.workflow.types import (
    ElementFeatures,
    ScreenFingerprint,
    WorkflowDocument,
    WorkflowStep,
)

SECRET_FIELD_HINTS = re.compile(
    r"(password|passwd|pwd|mfa|otp|totp|2fa|pin|secret|token|api[_-]?key|credential)",
    re.I,
)
OTP_LIKE = re.compile(r"^\d{4,8}$")
LONG_SECRET = re.compile(r"^[A-Za-z0-9+/=_-]{20,}$")

REDACTED = "[REDACTED]"


def sanitize_text(text: str, *, field_hint: str = "") -> tuple[str, bool]:
    """Remove passwords, MFA codes, OTP-like input. Returns (text, was_redacted)."""
    if not text:
        return text, False
    if SECRET_FIELD_HINTS.search(field_hint) or SECRET_FIELD_HINTS.search(text):
        return REDACTED, True
    if OTP_LIKE.match(text.strip()):
        return REDACTED, True
    if LONG_SECRET.match(text.strip()):
        return REDACTED, True
    return text, False


def sanitize_workflow_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy sanitize step payloads before persisting."""
    import copy

    doc = copy.deepcopy(data)
    for step in doc.get("steps", []):
        if step.get("kind") == "type" and step.get("text"):
            cleaned, redacted = sanitize_text(
                str(step["text"]),
                field_hint=str(step.get("element", {}).get("label_hint", "")),
            )
            step["text"] = cleaned
            step["sanitized"] = redacted or step.get("sanitized", False)
    return doc


@dataclass
class WorkflowRecorder:
    """Record clicks/inputs with screen fingerprints and relative element features."""

    capture: ScreenCapture = field(default_factory=ScreenCapture)
    validator: ResultValidator = field(default_factory=ResultValidator)
    anchor_region: ScreenRegion | None = None
    patch_size: int = 32
    on_log: Callable[[str], None] | None = None
    document: WorkflowDocument = field(default_factory=WorkflowDocument)
    _listening: bool = field(default=False, repr=False)
    _mouse_listener: Any = field(default=None, repr=False)
    _keyboard_listener: Any = field(default=None, repr=False)

    def _log(self, msg: str) -> None:
        if self.on_log:
            self.on_log(msg)

    def _anchor(self) -> ScreenRegion:
        if self.anchor_region is not None:
            return self.anchor_region
        w, h = self.capture.primary_monitor_size()
        return ScreenRegion(0, 0, w, h)

    def fingerprint_at(self, region: ScreenRegion | None = None) -> ScreenFingerprint:
        anchor = region or self._anchor()
        region_img = self.capture.capture_region(anchor)
        screen_img = self.capture.capture_screen()
        return ScreenFingerprint(
            anchor_left=anchor.left,
            anchor_top=anchor.top,
            anchor_width=anchor.width,
            anchor_height=anchor.height,
            region_hash=self.validator.image_hash(region_img),
            screen_hash=self.validator.image_hash(screen_img),
        )

    def _patch_b64(self, abs_x: int, abs_y: int) -> tuple[str, int, int]:
        half = self.patch_size // 2
        anchor = self._anchor()
        left = max(anchor.left, abs_x - half)
        top = max(anchor.top, abs_y - half)
        right = min(anchor.right, abs_x + half)
        bottom = min(anchor.bottom, abs_y + half)
        if right <= left or bottom <= top:
            return "", 0, 0
        patch = self.capture.capture_region(
            ScreenRegion(left, top, right - left, bottom - top)
        )
        buf = BytesIO()
        patch.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode("ascii"), patch.width, patch.height

    def record_click(
        self,
        abs_x: int,
        abs_y: int,
        *,
        role_hint: str = "unknown",
        label_hint: str = "",
        button: str = "left",
    ) -> WorkflowStep:
        anchor = self._anchor()
        rel_x = (abs_x - anchor.left) / anchor.width
        rel_y = (abs_y - anchor.top) / anchor.height
        rel_x = min(1.0, max(0.0, rel_x))
        rel_y = min(1.0, max(0.0, rel_y))
        patch_b64, pw, ph = self._patch_b64(abs_x, abs_y)
        step = WorkflowStep(
            kind="click",
            fingerprint=self.fingerprint_at(anchor),
            element=ElementFeatures(
                rel_x=rel_x,
                rel_y=rel_y,
                role_hint=role_hint,
                label_hint=label_hint,
                local_patch_b64=patch_b64 or None,
                patch_width=pw,
                patch_height=ph,
            ),
            abs_x=abs_x,
            abs_y=abs_y,
        )
        self.document.steps.append(step)
        self._log(f"Recorded click ({rel_x:.3f}, {rel_y:.3f}) btn={button}")
        return step

    def record_type(self, text: str, *, label_hint: str = "") -> WorkflowStep:
        cleaned, redacted = sanitize_text(text, field_hint=label_hint)
        step = WorkflowStep(
            kind="type",
            fingerprint=self.fingerprint_at(),
            element=ElementFeatures(
                rel_x=0.5,
                rel_y=0.5,
                role_hint="text_field",
                label_hint=label_hint,
            ),
            text=cleaned,
            sanitized=redacted,
        )
        self.document.steps.append(step)
        self._log("Recorded type (sanitized)" if redacted else "Recorded type")
        return step

    def record_key(self, key: str) -> WorkflowStep:
        step = WorkflowStep(
            kind="key",
            fingerprint=self.fingerprint_at(),
            element=ElementFeatures(rel_x=0.0, rel_y=0.0, role_hint="keyboard"),
            key=key,
        )
        self.document.steps.append(step)
        self._log(f"Recorded key {key!r}")
        return step

    def clear(self) -> None:
        self.document.steps.clear()

    def start_listening(self) -> None:
        if self._listening:
            return
        try:
            from pynput import keyboard, mouse
        except ImportError as exc:
            self._log(f"Input listeners unavailable: {exc}")
            return

        recorder = self

        def on_click(x, y, button, pressed):
            if not pressed:
                return
            if button.name != "left":
                return
            recorder.record_click(int(x), int(y), button=button.name)

        def on_press(key):
            try:
                char = key.char
            except AttributeError:
                char = None
            if char is not None and len(char) == 1:
                if SECRET_FIELD_HINTS.search(char):
                    return
                return
            name = getattr(key, "name", str(key))
            if name in ("enter", "tab", "esc", "backspace"):
                recorder.record_key(name)

        self._mouse_listener = mouse.Listener(on_click=on_click)
        self._keyboard_listener = keyboard.Listener(on_press=on_press)
        self._mouse_listener.start()
        self._keyboard_listener.start()
        self._listening = True
        self._log("Recording started (clicks + special keys; typed text via record_type)")

    def stop_listening(self) -> None:
        if not self._listening:
            return
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener = None
        self._listening = False
        self._log("Recording stopped")
