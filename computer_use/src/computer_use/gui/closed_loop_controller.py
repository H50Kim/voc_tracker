"""Background closed-loop runner for GUI (no Qt imports)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from computer_use.agent.adapters import AdapterBundle, make_phase1_adapters, stub_adapters
from computer_use.agent.ledger import AgentLedger, JsonFileLedger, LedgerSnapshot
from computer_use.agent.loop import RunOutcome, RunResult, restore_from_ledger, step_computer_use
from computer_use.agent.types import Action, AgentPolicy, LoopContext, Phase, SafetyDecision
from computer_use.core.region import ScreenRegion
from computer_use.gui.log_mask import mask_log_line
from computer_use.gui.paths import default_ledger_path
from computer_use.modes.types import AutomationMode
from computer_use.policy.policy_guard import PolicyGuard
from computer_use.agents.pipeline import AgentPipeline

ConfirmationHandler = Callable[[Action, str], SafetyDecision]
LogHandler = Callable[[str], None]
PhaseHandler = Callable[[Phase, RunResult | None], None]
RunFinishedHandler = Callable[[RunResult], None]


class RunnerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


@dataclass
class ClosedLoopConfig:
    goal: str
    mode: AutomationMode = AutomationMode.LOCAL
    region: ScreenRegion | None = None
    window_handle: int | None = None
    remote_inner_region: ScreenRegion | None = None
    dry_run: bool = True
    policy: AgentPolicy = field(default_factory=AgentPolicy)
    ledger_path: Path | None = None
    max_steps: int = 200
    ui_recovery: bool = False
    adapters: AdapterBundle | None = None


class ClosedLoopController:
    """Runs `step_computer_use` on a worker thread with pause/stop/confirm hooks."""

    def __init__(
        self,
        *,
        ledger: AgentLedger | None = None,
        policy_guard: PolicyGuard | None = None,
        on_log: LogHandler | None = None,
        on_phase: PhaseHandler | None = None,
        on_finished: RunFinishedHandler | None = None,
        request_confirmation: ConfirmationHandler | None = None,
        focus_window: Callable[[int], bool] | None = None,
    ) -> None:
        self._ledger = ledger or JsonFileLedger(default_ledger_path())
        self._policy_guard = policy_guard
        self._on_log = on_log
        self._on_phase = on_phase
        self._on_finished = on_finished
        self._request_confirmation = request_confirmation
        self._focus_window = focus_window

        self._thread: threading.Thread | None = None
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_event = threading.Event()
        self._state = RunnerState.IDLE
        self._lock = threading.Lock()
        self._context: LoopContext | None = None
        self._config: ClosedLoopConfig | None = None
        self._auth_reobserve_pending = False
        self._remote_health_stop = False
        self._agent_pipeline = AgentPipeline()
        self._agent_pipeline.startup()

    @property
    def state(self) -> RunnerState:
        with self._lock:
            return self._state

    @property
    def ledger(self) -> AgentLedger:
        return self._ledger

    @property
    def context(self) -> LoopContext | None:
        return self._context

    def load_startup_snapshot(self) -> LedgerSnapshot | None:
        return self._ledger.load()

    @property
    def agent_pipeline(self) -> AgentPipeline:
        return self._agent_pipeline

    def log(self, message: str) -> None:
        line = mask_log_line(message)
        if self._on_log:
            self._on_log(line)

    def start(self, config: ClosedLoopConfig) -> bool:
        with self._lock:
            if self._state in (RunnerState.RUNNING, RunnerState.STOPPING):
                return False
            self._config = config
            self._stop_event.clear()
            self._pause_event.set()
            self._state = RunnerState.RUNNING
            self._context = None
        self._thread = threading.Thread(target=self._run_loop, name="closed-loop", daemon=True)
        self._thread.start()
        return True

    def pause(self) -> None:
        with self._lock:
            if self._state != RunnerState.RUNNING:
                return
            self._state = RunnerState.PAUSED
        self._pause_event.clear()
        self.log("Paused (user)")

    def resume(self, *, ui_recovery: bool = False) -> None:
        with self._lock:
            if self._state != RunnerState.PAUSED:
                return
            self._state = RunnerState.RUNNING
            if self._config is not None:
                self._config.ui_recovery = (
                    ui_recovery or self._config.ui_recovery or self._auth_reobserve_pending
                )
            if self._auth_reobserve_pending and self._context is not None:
                self._context.phase = Phase.OBSERVE
                self._auth_reobserve_pending = False
        self._pause_event.set()
        self.log("Resumed")

    @property
    def auth_reobserve_pending(self) -> bool:
        return self._auth_reobserve_pending

    def resume_after_auth_pause(self) -> None:
        """User completed MFA/sign-in — continue with REOBSERVE at OBSERVE."""
        self.resume(ui_recovery=True)

    def stop(self, *, emergency: bool = False) -> None:
        with self._lock:
            if self._state == RunnerState.IDLE:
                return
            self._state = RunnerState.STOPPING
        self._stop_event.set()
        self._pause_event.set()
        label = "Emergency stop" if emergency else "Stop requested"
        self.log(label)

    def join(self, timeout: float | None = 5.0) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run_loop(self) -> None:
        config = self._config
        if config is None:
            return

        if config.ledger_path is not None:
            self._ledger = JsonFileLedger(config.ledger_path)

        ctx = LoopContext()
        snap = self._ledger.load()
        if snap is not None:
            restore_from_ledger(ctx, snap)
            if ctx.pending_operation and not ctx.pending_operation.resolved:
                self.log(
                    f"Loaded unresolved pending op {ctx.pending_operation.operation_id} "
                    "(mutating re-execute blocked)"
                )

        if config.window_handle and self._focus_window:
            if self._focus_window(config.window_handle):
                self.log(f"Focused window #{config.window_handle}")

        browser_ctrl = None
        remote_ctrl = None
        if config.mode == AutomationMode.BROWSER:
            from computer_use.modes.browser import default_browser_controller

            browser_ctrl = default_browser_controller()
        if config.mode == AutomationMode.REMOTE:
            from computer_use.modes.remote import default_remote_controller

            remote_ctrl = default_remote_controller()

        if config.adapters is not None:
            adapters = config.adapters
        else:
            adapters = make_phase1_adapters(
                dry_run=config.dry_run,
                policy=self._policy_guard,
                region=config.region,
                mode=config.mode,
                window_handle=config.window_handle,
                browser_controller=browser_ctrl,
                remote_controller=remote_ctrl,
                remote_inner_region=config.remote_inner_region,
                request_confirmation=self._request_confirmation,
                agent_pipeline=self._agent_pipeline,
            )

        goal = config.goal.strip() or "(empty goal)"
        self.log(f"Run start — goal: {goal!r}, mode: {config.mode.value}")

        trace: list[Phase] = []
        terminal = {Phase.SUCCESS, Phase.INCOMPLETE}
        steps = 0
        last_result: RunResult | None = None

        while steps < config.max_steps and not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                break
            if ctx.phase in terminal:
                break

            if (
                browser_ctrl is not None
                and config.window_handle
                and self._state == RunnerState.RUNNING
            ):
                auth = browser_ctrl.check_auth_for_handle(config.window_handle)
                if auth is not None:
                    ctx.phase = Phase.PAUSED
                    self._auth_reobserve_pending = True
                    with self._lock:
                        self._state = RunnerState.PAUSED
                    self._pause_event.clear()
                    self.log(f"Auth pause: {auth.reason}")
                    if self._on_phase:
                        self._on_phase(ctx.phase, None)
                    continue

            if (
                remote_ctrl is not None
                and config.window_handle
                and self._state == RunnerState.RUNNING
            ):
                from computer_use.controllers.remote_controller import SessionHealthAction

                last_image = None
                if ctx.last_observation and ctx.last_observation.payload is not None:
                    last_image = ctx.last_observation.payload
                health = remote_ctrl.check_session_health(
                    config.window_handle,
                    latest_capture=last_image,
                )
                if health is not None:
                    if health.action == SessionHealthAction.STOP:
                        self._remote_health_stop = True
                        self.log(f"Remote session stop: {health.reason}")
                        self._stop_event.set()
                        if self._on_phase:
                            self._on_phase(Phase.INCOMPLETE, None)
                        break
                    ctx.phase = Phase.PAUSED
                    with self._lock:
                        self._state = RunnerState.PAUSED
                    self._pause_event.clear()
                    self.log(f"Remote session pause: {health.reason}")
                    if self._on_phase:
                        self._on_phase(ctx.phase, None)
                    continue

            result = step_computer_use(
                goal,
                ctx,
                adapters=adapters,
                policy=config.policy,
                ledger=self._ledger,
                clock=time.time,
                ui_recovery=config.ui_recovery,
            )
            last_result = result
            config.ui_recovery = False
            trace.extend(result.trace)
            steps += 1
            self._context = ctx
            if self._on_phase:
                self._on_phase(ctx.phase, result)
            phase_names = " → ".join(p.value for p in result.trace)
            outcome = result.outcome.value if result.outcome else "—"
            self.log(f"Phase: {phase_names} | outcome={outcome}")

            if result.outcome == RunOutcome.BLOCKED:
                break
            if ctx.phase in terminal:
                break

        if self._stop_event.is_set() and ctx.phase not in terminal:
            ctx.phase = Phase.INCOMPLETE
            self._ledger.mark_run_outcome(RunOutcome.INCOMPLETE.value)

        if last_result and last_result.outcome == RunOutcome.BLOCKED:
            final_outcome = RunOutcome.BLOCKED
        elif ctx.phase == Phase.SUCCESS:
            final_outcome = RunOutcome.SUCCESS
        elif ctx.phase == Phase.INCOMPLETE:
            final_outcome = RunOutcome.INCOMPLETE
        else:
            final_outcome = None

        final = RunResult(outcome=final_outcome, phase=ctx.phase, context=ctx, trace=trace)
        self.log(f"Run finished: phase={ctx.phase.value}, outcome={final_outcome}")

        with self._lock:
            self._state = RunnerState.IDLE
            self._config = None
        if self._on_finished:
            self._on_finished(final)
