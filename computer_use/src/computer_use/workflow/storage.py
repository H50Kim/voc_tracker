from __future__ import annotations

import json
from pathlib import Path

from computer_use.workflow.recorder import sanitize_workflow_dict
from computer_use.workflow.types import WorkflowDocument


def default_workflows_dir() -> Path:
    return Path.home() / ".computer_use" / "workflows"


def save_workflow(path: Path, document: WorkflowDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = sanitize_workflow_dict(document.to_dict())
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_workflow(path: Path) -> WorkflowDocument:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = sanitize_workflow_dict(data)
    return WorkflowDocument.from_dict(data)
