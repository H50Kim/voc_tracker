from pathlib import Path

from PIL import Image

from computer_use.core.region import ScreenRegion
from computer_use.workflow.recorder import (
    REDACTED,
    WorkflowRecorder,
    sanitize_text,
    sanitize_workflow_dict,
)
from computer_use.workflow.storage import load_workflow, save_workflow
from computer_use.workflow.types import WorkflowDocument


class _FakeCapture:
    def capture_region(self, region: ScreenRegion) -> Image.Image:
        return Image.new("RGB", (max(region.width, 1), max(region.height, 1)))

    def capture_screen(self) -> Image.Image:
        return Image.new("RGB", (64, 48))

    def primary_monitor_size(self) -> tuple[int, int]:
        return 64, 48


def _recorder() -> WorkflowRecorder:
    return WorkflowRecorder(capture=_FakeCapture(), anchor_region=ScreenRegion(0, 0, 64, 48))


def test_sanitize_text_password_hint():
    out, redacted = sanitize_text("MySecret123!", field_hint="password field")
    assert redacted
    assert out == REDACTED


def test_sanitize_text_otp():
    out, redacted = sanitize_text("123456")
    assert redacted
    assert out == REDACTED


def test_sanitize_text_normal():
    out, redacted = sanitize_text("hello world")
    assert not redacted
    assert out == "hello world"


def test_record_type_redacts_mfa_in_label():
    rec = _recorder()
    step = rec.record_type("999888", label_hint="Enter MFA code")
    assert step.text == REDACTED
    assert step.sanitized


def test_sanitize_workflow_dict_on_save_roundtrip(tmp_path: Path):
    doc = WorkflowDocument(name="t", steps=[])
    rec = _recorder()
    rec.document = doc
    rec.record_type("654321", label_hint="otp")
    path = tmp_path / "wf.json"
    save_workflow(path, rec.document)
    raw = path.read_text()
    assert "654321" not in raw
    loaded = load_workflow(path)
    assert loaded.steps[0].text == REDACTED


def test_sanitize_workflow_dict_preserves_safe_text():
    data = {
        "version": 1,
        "steps": [
            {
                "kind": "type",
                "text": "open settings",
                "element": {"label_hint": "search"},
                "fingerprint": {
                    "anchor_left": 0,
                    "anchor_top": 0,
                    "anchor_width": 10,
                    "anchor_height": 10,
                    "region_hash": "abc",
                },
                "element": {
                    "rel_x": 0.5,
                    "rel_y": 0.5,
                    "role_hint": "text_field",
                    "label_hint": "search",
                },
            }
        ],
    }
    # fix duplicate element key - use proper structure
    data["steps"][0] = {
        "kind": "type",
        "text": "open settings",
        "fingerprint": {
            "anchor_left": 0,
            "anchor_top": 0,
            "anchor_width": 10,
            "anchor_height": 10,
            "region_hash": "abc",
        },
        "element": {
            "rel_x": 0.5,
            "rel_y": 0.5,
            "role_hint": "text_field",
            "label_hint": "search",
        },
    }
    cleaned = sanitize_workflow_dict(data)
    assert cleaned["steps"][0]["text"] == "open settings"
