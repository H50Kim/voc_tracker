"""Safe adapters and Phase 1 wiring stubs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol

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

if TYPE_CHECKING:
    from computer_use.controllers.browser_controller import BrowserController
    from computer_use.controllers.remote_controller import RemoteController
    from computer_use.vision.coordinate_mapper import CoordinateMapper

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
    """Deterministic stub when AI pipeline is disabled."""
    from computer_use.ai.interpret_service import observation_fingerprint

    fp = observation_fingerprint(observation)
    return Interpretation(
        summary=f"frame:{observation.frame_id}",
        targets={},
        fingerprint=fp,
        confidence=0.0,
    )


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
    window_handle: int | None = None,
    browser_controller: BrowserController | None = None,
    remote_controller: RemoteController | None = None,
    remote_inner_region: ScreenRegion | None = None,
    request_confirmation: ConfirmationHandler | None = None,
    use_ai: bool | None = None,
    agent_pipeline=None,
) -> AdapterBundle:
    capture = ScreenCapture()
    controller = InputController(policy=policy or DEFAULT_POLICY, dry_run=dry_run)
    from computer_use.ai.llm_policy import ai_pipeline_enabled
    from computer_use.ai.result_validator import ExtendedResultValidator

    validator = ResultValidator()
    extended_validator = ExtendedResultValidator(core=validator)
    _ai_enabled = ai_pipeline_enabled() if use_ai is None else use_ai
    _mode = mode
    _window_handle = window_handle
    _browser = browser_controller
    _remote = remote_controller
    _remote_inner = remote_inner_region
    _mapper: CoordinateMapper | None = None

    def _refresh_remote_mapper() -> CoordinateMapper | None:
        nonlocal _mapper
        if _mode != AutomationMode.REMOTE or _remote is None or _window_handle is None:
            return None
        if _remote_inner is None:
            return None
        mapper = _remote.coordinate_mapper(
            window_handle=_window_handle,
            inner_relative=_remote_inner,
            user_region=region,
        )
        if mapper is None:
            _mapper = None
            return None
        if _mapper is not None:
            refreshed = _remote.refresh_mapper(_window_handle, _mapper)
            if refreshed is not None:
                mapper = refreshed
        _mapper = mapper
        return _mapper

    def _effective_region() -> ScreenRegion | None:
        if _mode == AutomationMode.BROWSER and _browser is not None:
            return _browser.capture_region_for(
                window_handle=_window_handle,
                user_region=region,
            )
        if _mode == AutomationMode.REMOTE and _remote is not None:
            return _remote.capture_region_for(
                window_handle=_window_handle,
                inner_relative=_remote_inner,
                user_region=region,
            )
        return region

    def observe() -> Observation:
        if _mode == AutomationMode.REMOTE:
            _refresh_remote_mapper()
        eff = _effective_region()
        if eff is not None:
            image = capture.capture_region(eff)
            frame = f"{_mode.value}:region:{eff.left},{eff.top}"
            if _window_handle:
                frame = f"{frame}:hwnd:{_window_handle}"
            if _mode == AutomationMode.REMOTE and _remote_inner is not None:
                frame = (
                    f"{frame}:inner:{_remote_inner.left},{_remote_inner.top},"
                    f"{_remote_inner.width}x{_remote_inner.height}"
                )
            return Observation(frame_id=frame, payload=image)
        return safe_observe(capture=capture, frame_id=_mode.value)

    _interpret_fn = None
    _generate_fn = None
    _glean_log: list[str] = []

    if _ai_enabled:
        from computer_use.agents.pipeline import AgentPipeline
        from computer_use.ai.interpret_service import InterpretConfig, build_interpret_fn
        from computer_use.ai.ollama_client import OllamaClient
        from computer_use.ai.planner_adapters import make_generate_candidates_fn
        from computer_use.ai.task_planner import TaskPlanner
        from computer_use.ai.glean_helper import suggest_glean_search_in_edge

        pipeline = agent_pipeline or AgentPipeline()
        if not pipeline.model_manager.hardware:
            pipeline.startup()
        ollama = pipeline.model_manager.ollama or OllamaClient()
        rec = pipeline.model_manager.recommendation
        text_model = rec.text_model if rec else "llama3.2"
        interpret_cfg = InterpretConfig(
            window_handle=_window_handle,
            model_manager=pipeline.model_manager,
            ollama=ollama,
        )
        _interpret_fn = build_interpret_fn(interpret_cfg)
        planner = TaskPlanner(client=ollama, text_model=text_model)
        _plan_holder: dict[str, object] = {"plan": None}
        _step_holder: dict[str, int] = {"index": 0}
        _generate_fn = make_generate_candidates_fn(
            planner,
            plan_holder=_plan_holder,  # type: ignore[arg-type]
            step_index_holder=_step_holder,
        )

    def interpret(observation: Observation) -> Interpretation:
        if _interpret_fn is not None:
            return _interpret_fn(observation)
        return safe_interpret(observation)

    def generate(interpretation: Interpretation, *, goal: str) -> list[Action]:
        if _browser is not None and _mode == AutomationMode.BROWSER:
            from computer_use.ai.glean_helper import suggest_glean_search_in_edge

            suggestion = suggest_glean_search_in_edge(
                goal,
                browser=_browser,
                preferred_handle=_window_handle,
            )
            if suggestion is not None and suggestion.message not in _glean_log:
                _glean_log.append(suggestion.message)
        if _generate_fn is not None:
            return _generate_fn(interpretation, goal=goal)
        return default_generate_candidates(interpretation, goal=goal)

    def safety(action: Action, *, goal: str) -> SafetyDecision:
        decision = policy_safety_gate(action, goal=goal, policy=policy)
        if not decision.approved:
            return decision
        if request_confirmation is not None:
            return request_confirmation(action, goal)
        return decision

    def execute(action: Action) -> ExecutionOutcome:
        eff = _effective_region()
        screen_x, screen_y = action.x, action.y
        if (
            eff is not None
            and action.x is not None
            and action.y is not None
            and _mode in (AutomationMode.BROWSER, AutomationMode.REMOTE)
        ):
            in_capture_bounds = (
                eff.left <= action.x < eff.right and eff.top <= action.y < eff.bottom
            )
            if _mode == AutomationMode.REMOTE:
                mapper = _refresh_remote_mapper()
                if mapper is not None:
                    if in_capture_bounds:
                        rel_x = action.x - eff.left
                        rel_y = action.y - eff.top
                    else:
                        rel_x, rel_y = action.x, action.y
                    mapped = mapper.capture_relative_to_screen(rel_x, rel_y)
                    if mapped is None:
                        return ExecutionOutcome.UNKNOWN
                    screen_x, screen_y = mapped
                elif not in_capture_bounds:
                    return ExecutionOutcome.UNKNOWN
            elif not in_capture_bounds:
                return ExecutionOutcome.UNKNOWN
        if screen_x is not None and screen_y is not None:
            mapped_action = Action(
                kind=action.kind,
                semantic_operation_key=action.semantic_operation_key,
                description=action.description,
                target_id=action.target_id,
                x=screen_x,
                y=screen_y,
            )
            return safe_execute(mapped_action, controller=controller)
        return safe_execute(action, controller=controller)

    def verify(
        action: Action,
        *,
        before: Observation | None,
        after: Observation | None,
    ) -> ExecutionOutcome:
        outcome = safe_verify(action, before=before, after=after, validator=validator)
        if outcome == ExecutionOutcome.SUCCESS:
            return outcome
        if before and after and before.payload is not None and after.payload is not None:
            hook = extended_validator.validate_screen_change(before.payload, after.payload)
            if hook.passed:
                return ExecutionOutcome.SUCCESS
        return outcome

    def result_query(pending_semantic_key: str) -> ExecutionOutcome:
        import os

        expect_path = os.environ.get("COMPUTER_USE_VERIFY_FILE", "").strip()
        if expect_path:
            hook = extended_validator.validate_file_exists(expect_path)
            if hook.passed:
                return ExecutionOutcome.SUCCESS
        if pending_semantic_key.startswith("plan:glean"):
            return ExecutionOutcome.UNKNOWN
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
