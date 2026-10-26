from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

StepKind = Literal["click", "type", "key"]


@dataclass
class ScreenFingerprint:
    """Visual anchor for replay verification (hashes, not secrets)."""

    anchor_left: int
    anchor_top: int
    anchor_width: int
    anchor_height: int
    region_hash: str
    screen_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_left": self.anchor_left,
            "anchor_top": self.anchor_top,
            "anchor_width": self.anchor_width,
            "anchor_height": self.anchor_height,
            "region_hash": self.region_hash,
            "screen_hash": self.screen_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreenFingerprint:
        return cls(
            anchor_left=int(data["anchor_left"]),
            anchor_top=int(data["anchor_top"]),
            anchor_width=int(data["anchor_width"]),
            anchor_height=int(data["anchor_height"]),
            region_hash=str(data["region_hash"]),
            screen_hash=data.get("screen_hash"),
        )


@dataclass
class ElementFeatures:
    """UI target hints: relative position within anchor + optional local patch."""

    rel_x: float
    rel_y: float
    role_hint: str = "unknown"
    label_hint: str = ""
    local_patch_b64: str | None = None
    patch_width: int = 0
    patch_height: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rel_x": self.rel_x,
            "rel_y": self.rel_y,
            "role_hint": self.role_hint,
            "label_hint": self.label_hint,
            "local_patch_b64": self.local_patch_b64,
            "patch_width": self.patch_width,
            "patch_height": self.patch_height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ElementFeatures:
        return cls(
            rel_x=float(data["rel_x"]),
            rel_y=float(data["rel_y"]),
            role_hint=str(data.get("role_hint", "unknown")),
            label_hint=str(data.get("label_hint", "")),
            local_patch_b64=data.get("local_patch_b64"),
            patch_width=int(data.get("patch_width", 0)),
            patch_height=int(data.get("patch_height", 0)),
        )


@dataclass
class WorkflowStep:
    kind: StepKind
    fingerprint: ScreenFingerprint
    element: ElementFeatures
    abs_x: int | None = None
    abs_y: int | None = None
    text: str | None = None
    key: str | None = None
    sanitized: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind,
            "fingerprint": self.fingerprint.to_dict(),
            "element": self.element.to_dict(),
            "sanitized": self.sanitized,
        }
        if self.abs_x is not None:
            out["abs_x"] = self.abs_x
        if self.abs_y is not None:
            out["abs_y"] = self.abs_y
        if self.text is not None:
            out["text"] = self.text
        if self.key is not None:
            out["key"] = self.key
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            kind=data["kind"],
            fingerprint=ScreenFingerprint.from_dict(data["fingerprint"]),
            element=ElementFeatures.from_dict(data["element"]),
            abs_x=data.get("abs_x"),
            abs_y=data.get("abs_y"),
            text=data.get("text"),
            key=data.get("key"),
            sanitized=bool(data.get("sanitized", False)),
        )


@dataclass
class WorkflowDocument:
    version: int = 1
    name: str = "untitled"
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowDocument:
        return cls(
            version=int(data.get("version", 1)),
            name=str(data.get("name", "untitled")),
            description=str(data.get("description", "")),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
        )
