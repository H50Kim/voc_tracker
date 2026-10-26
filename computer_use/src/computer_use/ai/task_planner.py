"""Natural-language goal → structured step plan (Ollama or deterministic fallback)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from computer_use.agent.types import ActionKind
from computer_use.ai.llm_policy import ai_pipeline_enabled
from computer_use.ai.ollama_client import OllamaClient, OllamaError


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    kind: ActionKind
    description: str
    semantic_operation_key: str
    target_id: str | None = None


@dataclass
class TaskPlan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    source: str = "heuristic"

    def current_step(self, index: int) -> PlanStep | None:
        if index < 0 or index >= len(self.steps):
            return None
        return self.steps[index]


class TaskPlanner:
    def __init__(
        self,
        *,
        client: OllamaClient | None = None,
        text_model: str = "llama3.2",
    ) -> None:
        self._client = client
        self.text_model = text_model

    def plan(self, goal: str) -> TaskPlan:
        goal = goal.strip()
        if not goal:
            return TaskPlan(goal=goal, steps=[], source="empty")
        if ai_pipeline_enabled() and self._client is not None:
            try:
                steps = self._plan_via_ollama(goal)
                if steps:
                    return TaskPlan(goal=goal, steps=steps, source="ollama")
            except OllamaError:
                pass
        return heuristic_plan(goal)

    def _plan_via_ollama(self, goal: str) -> list[PlanStep]:
        assert self._client is not None
        system = (
            "You are a UI automation planner. Output JSON only: "
            '{"steps":[{"id":"s1","kind":"click|type|key|observe","description":"...",'
            '"semantic_key":"op:name","target_id":"optional"}]}'
        )
        raw = self._client.chat(
            model=self.text_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Goal: {goal}"},
            ],
            format_json=True,
        )
        return _parse_plan_json(raw, goal)


def heuristic_plan(goal: str) -> TaskPlan:
    """Deterministic fallback when Ollama is down (CI-safe)."""
    lower = goal.lower()
    steps: list[PlanStep] = []
    if "glean" in lower:
        query = _extract_quoted_or_tail(goal) or goal
        steps.append(
            PlanStep(
                step_id="s1",
                kind=ActionKind.OBSERVE,
                description=f"Reference: Glean search «{query}» (read-only)",
                semantic_operation_key="plan:glean_reference",
                target_id=None,
            )
        )
    if re.search(r"\btype\b|입력|텍스트", goal, re.I):
        text = _extract_quoted_or_tail(goal) or "text"
        steps.append(
            PlanStep(
                step_id="s2",
                kind=ActionKind.TYPE,
                description=f"Type: {text}",
                semantic_operation_key="plan:type",
                target_id="input",
            )
        )
    if re.search(r"\bclick\b|클릭|press|버튼", goal, re.I) or not steps:
        steps.append(
            PlanStep(
                step_id="s0",
                kind=ActionKind.CLICK,
                description=f"Primary UI action for: {goal[:80]}",
                semantic_operation_key="plan:primary_click",
                target_id="primary",
            )
        )
    return TaskPlan(goal=goal, steps=steps, source="heuristic")


def _extract_quoted_or_tail(text: str) -> str | None:
    match = re.search(r'["\']([^"\']+)["\']', text)
    if match:
        return match.group(1).strip()
    for sep in (":", "—", "-"):
        if sep in text:
            tail = text.rsplit(sep, 1)[-1].strip()
            if tail and len(tail) < 120:
                return tail
    return None


def _parse_plan_json(raw: str, goal: str) -> list[PlanStep]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return heuristic_plan(goal).steps
    steps: list[PlanStep] = []
    for idx, entry in enumerate(data.get("steps") or []):
        kind_str = str(entry.get("kind") or "click").lower()
        try:
            kind = ActionKind(kind_str)
        except ValueError:
            kind = ActionKind.CLICK
        steps.append(
            PlanStep(
                step_id=str(entry.get("id") or f"s{idx}"),
                kind=kind,
                description=str(entry.get("description") or goal),
                semantic_operation_key=str(entry.get("semantic_key") or f"plan:step{idx}"),
                target_id=entry.get("target_id"),
            )
        )
    return steps
