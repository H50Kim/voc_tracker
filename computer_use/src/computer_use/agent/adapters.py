"""Safe adapters and Phase 1 wiring stubs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from computer_use.agent.types import (
    Action,
    ActionKind,
    ExecutionOutcome,
    Interpretation,
    Observation,
    SafetyDecision,
)
from computer_use.core.capture import ScreenCapture
from computer_use.core.input_control import InputController
from computer_use.core.region import ScreenRegion
from computer_use.core.validator import ResultValidator
from computer_use.modes.types import AutomationMode
from computer_use.policy.policy_guard import DEFAULT_POLICY, PolicyGuard

ConfirmationHandler = Callable[[Action, str], SafetyDecision]


class ObserveFn(Protocol):
    def __call__(self) -> Observation: ...


class InterpretFn(Protocol):
    def __call__(self, observation: Observation) -> Interpretation: ...


class GenerateCandidatesFn(Protocol):
    def __call__(self, interpretation: Interpretation, *, goal: str) -> list[Action]: ...


class SafetyGateFn(Protocol):
    def __call__(self, action: Action, *, goal: str) -> SafetyDecision: ...


class ExecuteFn(Protocol):
    def __call__(self, action: Action) -> ExecutionOutcome: ...


class VerifyFn(Protocol):
    def __call__(
        self,
        action: Action,
        *,
        before: Observation | None,
        after: Observation | None,
    ) -> ExecutionOutcome: ...


class ResultQueryFn(Protocol):
    def __call__(self, pending_semantic_key: str) -> ExecutionOutcome: ...


@dataclass
class AdapterBundle:
    observe: ObserveFn
    interpret: InterpretFn
    generate_candidates: GenerateCandidatesFn
    safety_gate: SafetyGateFn
    execute: ExecuteFn
    verify: VerifyFn
    result_query: ResultQueryFn


def safe_observe(*, capture: ScreenCapture | None = None, frame_id: str = "live") -> Observation:
    cap = capture or ScreenCapture()
    image = cap.capture_screen()
    return Observation(frame_id=frame_id, payload=image)


def safe_interpret(observation: Observation) -> Interpretation:
    return Interpretation(summary=f"frame:{observation.frame_id}", targets={})


def default_generate_candidates(interpretation: Interpretation, *, goal: str) -> list[Action]:
    _ = interpretation
    return [
        Action(
            kind=ActionKind.CLICK,
            semantic_operation_key=f"goal:{goal}",
            description=f"Primary action for {goal}",
            target_id="primary",
        )
    ]


def safe_execute(action: Action, *, controller: InputController | None = None) -> ExecutionOutcome:
    ctrl = controller or InputController(policy=DEFAULT_POLICY, dry_run=True)
    try:
        if action.kind == ActionKind.CLICK and action.x is not None and action.y is not None:
            ctrl.click(action.x, action.y, action_label=action.description)
        elif action.kind == ActionKind.TYPE:
            ctrl.type_text(action.description, action_label=action.description)
        elif action.kind == ActionKind.KEY:
            ctrl.press_key(action.description, action_label=action.description)
        elif action.kind in (ActionKind.OBSERVE, ActionKind.QUERY):
            return ExecutionOutcome.SUCCESS
        return ExecutionOutcome.SUCCESS
    except Exception:
        return ExecutionOutcome.UNKNOWN


def safe_verify(
    action: Action,
    *,
    before: Observation | None,
    after: Observation | None,
    validator: ResultValidator | None = None,
) -> ExecutionOutcome:
    _ = action
    val = validator or ResultValidator()
    if before is None or after is None:
        return ExecutionOutcome.UNKNOWN
    if before.payload is None or after.payload is None:
        return ExecutionOutcome.UNKNOWN
    result = val.validate_changed(before.payload, after.payload)
    if result.passed:
        return ExecutionOutcome.SUCCESS
    return ExecutionOutcome.FAILURE


def policy_safety_gate(action: Action, *, goal: str, policy: PolicyGuard | None = None) -> SafetyDecision:
    guard = policy or DEFAULT_POLICY
    try:
        guard.check_text_action(action.description)
        guard.check_text_action(goal)
        if action.kind == ActionKind.KEY:
            guard.check_key_action(action.semantic_operation_key)
    except Exception as exc:
        return SafetyDecision(approved=False, reason=str(exc))
    return SafetyDecision(approved=True)


def make_phase1_adapters(
    *,
    dry_run: bool = True,
    policy: PolicyGuard | None = None,
    region: ScreenRegion | None = None,
    mode: AutomationMode = AutomationMode.LOCAL,
    request_confirmation: ConfirmationHandler | None = None,
) -> AdapterBundle:
    capture = ScreenCapture()
    controller = InputController(policy=policy or DEFAULT_POLICY, dry_run=dry_run)
    validator = ResultValidator()
    _mode = mode

    def observe() -> Observation:
        if region is not None:
            image = capture.capture_region(region)
            return Observation(
                frame_id=f"{_mode.value}:region:{region.left},{region.top}",
                payload=image,
            )
        return safe_observe(capture=capture, frame_id=_mode.value)

    def interpret(observation: Observation) -> Interpretation:
        return safe_interpret(observation)

    def generate(interpretation: Interpretation, *, goal: str) -> list[Action]:
        return default_generate_candidates(interpretation, goal=goal)

    def safety(action: Action, *, goal: str) -> SafetyDecision:
        decision = policy_safety_gate(action, goal=goal, policy=policy)
        if not decision.approved:
            return decision
        if request_confirmation is not None:
            return request_confirmation(action, goal)
        return decision

    def execute(action: Action) -> ExecutionOutcome:
        return safe_execute(action, controller=controller)

    def verify(
        action: Action,
        *,
        before: Observation | None,
        after: Observation | None,
    ) -> ExecutionOutcome:
        return safe_verify(action, before=before, after=after, validator=validator)

    def result_query(_pending_semantic_key: str) -> ExecutionOutcome:
        return ExecutionOutcome.UNKNOWN

    return AdapterBundle(
        observe=observe,
        interpret=interpret,
        generate_candidates=generate,
        safety_gate=safety,
        execute=execute,
        verify=verify,
        result_query=result_query,
    )


def stub_adapters(
    *,
    observe: ObserveFn | None = None,
    interpret: InterpretFn | None = None,
    generate_candidates: GenerateCandidatesFn | None = None,
    safety_gate: SafetyGateFn | None = None,
    execute: ExecuteFn | None = None,
    verify: VerifyFn | None = None,
    result_query: ResultQueryFn | None = None,
) -> AdapterBundle:
    """Build injectable stub bundle for tests."""

    def _observe() -> Observation:
        return Observation(frame_id="stub")

    def _interpret(obs: Observation) -> Interpretation:
        return Interpretation(summary=obs.frame_id, targets={"t": (1, 2)})

    def _gen(interp: Interpretation, *, goal: str) -> list[Action]:
        return [
            Action(
                kind=ActionKind.CLICK,
                semantic_operation_key=f"stub:{goal}",
                description="stub click",
                target_id="t",
                x=interp.targets.get("t", (0, 0))[0],
                y=interp.targets.get("t", (0, 0))[1],
            )
        ]

    def _safety(action: Action, *, goal: str) -> SafetyDecision:
        _ = goal
        return SafetyDecision(approved=True)

    def _execute(action: Action) -> ExecutionOutcome:
        _ = action
        return ExecutionOutcome.SUCCESS

    def _verify(
        action: Action,
        *,
        before: Observation | None,
        after: Observation | None,
    ) -> ExecutionOutcome:
        _ = action, before, after
        return ExecutionOutcome.SUCCESS

    def _query(key: str) -> ExecutionOutcome:
        _ = key
        return ExecutionOutcome.UNKNOWN

    return AdapterBundle(
        observe=observe or _observe,
        interpret=interpret or _interpret,
        generate_candidates=generate_candidates or _gen,
        safety_gate=safety_gate or _safety,
        execute=execute or _execute,
        verify=verify or _verify,
        result_query=result_query or _query,
    )
