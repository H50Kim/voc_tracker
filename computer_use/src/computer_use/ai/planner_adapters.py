"""Bridge TaskPlan → Action candidates for closed-loop adapters."""

from __future__ import annotations

from computer_use.agent.types import Action, ActionKind, Interpretation
from computer_use.ai.task_planner import PlanStep, TaskPlan, TaskPlanner


def plan_step_to_actions(
    step: PlanStep,
    interpretation: Interpretation,
) -> list[Action]:
    target_id = step.target_id or "primary"
    x = y = None
    if target_id in interpretation.targets:
        x, y = interpretation.targets[target_id]
    elif interpretation.targets:
        first_key = next(iter(interpretation.targets))
        x, y = interpretation.targets[first_key]
        target_id = first_key
    return [
        Action(
            kind=step.kind,
            semantic_operation_key=step.semantic_operation_key,
            description=step.description,
            target_id=target_id,
            x=x,
            y=y,
            fingerprint=interpretation.fingerprint,
        )
    ]


def make_generate_candidates_fn(
    planner: TaskPlanner,
    *,
    plan_holder: dict[str, TaskPlan | None],
    step_index_holder: dict[str, int],
):
    from computer_use.agent.adapters import default_generate_candidates

    def generate(interpretation: Interpretation, *, goal: str) -> list[Action]:
        plan = plan_holder.get("plan")
        if plan is None:
            plan = planner.plan(goal)
            plan_holder["plan"] = plan
            step_index_holder["index"] = 0
        idx = step_index_holder.get("index", 0)
        step = plan.current_step(idx)
        if step is None:
            return default_generate_candidates(interpretation, goal=goal)
        actions = plan_step_to_actions(step, interpretation)
        mutating = [a for a in actions if a.kind in (ActionKind.CLICK, ActionKind.TYPE, ActionKind.KEY)]
        if mutating:
            return actions
        return default_generate_candidates(interpretation, goal=goal)

    return generate
