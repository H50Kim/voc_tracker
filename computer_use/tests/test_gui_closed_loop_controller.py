"""Closed-loop GUI controller tests (no Qt)."""

from __future__ import annotations

import threading
import time

from computer_use.agent.adapters import stub_adapters
from computer_use.agent.ledger import InMemoryLedger, LedgerSnapshot
from computer_use.agent.loop import RunOutcome
from computer_use.agent.types import (
    Action,
    ActionKind,
    ExecutionOutcome,
    Observation,
    PendingOperation,
    SafetyDecision,
)
from computer_use.controllers.browser_controller import StubEdgeWindowEnumerator
from computer_use.gui.closed_loop_controller import ClosedLoopConfig, ClosedLoopController, RunnerState
from computer_use.gui.log_mask import mask_log_line
from computer_use.modes.types import AutomationMode


def _stub_config(**kwargs) -> ClosedLoopConfig:
    base = {"goal": "test", "dry_run": True, "max_steps": 50, "adapters": stub_adapters()}
    base.update(kwargs)
    return ClosedLoopConfig(**base)


def test_mask_log_line_redacts_secrets():
    raw = "password=abc123 and token=xyz"
    masked = mask_log_line(raw)
    assert "abc123" not in masked
    assert "xyz" not in masked


def test_controller_pause_stop_on_background_thread():
    finished = threading.Event()

    def on_finished(result) -> None:
        _ = result
        finished.set()

    def slow_observe() -> Observation:
        time.sleep(0.25)
        return Observation(frame_id="slow")

    slow = stub_adapters(observe=slow_observe)
    ledger = InMemoryLedger()
    controller = ClosedLoopController(ledger=ledger, on_finished=on_finished)
    config = _stub_config(goal="test goal", adapters=slow, max_steps=100)
    assert controller.start(config)
    time.sleep(0.05)
    controller.pause()
    assert controller.state == RunnerState.PAUSED
    controller.resume()
    finished.wait(timeout=5.0)
    assert finished.is_set()
    assert controller.state == RunnerState.IDLE


def test_controller_loads_pending_without_auto_execute():
    action = Action(
        kind=ActionKind.CLICK,
        semantic_operation_key="op:x",
        description="click",
        operation_id="pending-1",
    )
    pending = PendingOperation(
        operation_id="pending-1",
        semantic_operation_key="op:x",
        action=action,
        execution_outcome=ExecutionOutcome.UNKNOWN,
        created_at_ms=1,
        ledger_recorded=True,
    )
    ledger = InMemoryLedger()
    ledger.seed(
        LedgerSnapshot(
            pending_operation=pending,
            execute_budget_used=0,
            result_query_count=0,
            semantic_retry_counts={},
        )
    )
    exec_calls: list[str] = []

    def execute(action):
        exec_calls.append(action.operation_id)
        return ExecutionOutcome.SUCCESS

    adapters = stub_adapters(execute=execute)
    finished = threading.Event()
    controller = ClosedLoopController(
        ledger=ledger,
        request_confirmation=lambda _a, _g: SafetyDecision(approved=True),
        on_finished=lambda _r: finished.set(),
    )
    controller.start(_stub_config(goal="g", max_steps=8, adapters=adapters))
    finished.wait(timeout=5.0)
    assert finished.is_set()
    assert "pending-1" not in exec_calls


def test_browser_auth_pause_triggers_runner_paused(monkeypatch):
    class SignInStub(StubEdgeWindowEnumerator):
        def get_window_title(self, handle: int) -> str:
            return "Sign in to your account - Microsoft Edge"

    monkeypatch.setattr(
        "computer_use.modes.browser.default_browser_controller",
        lambda **_: __import__(
            "computer_use.controllers.browser_controller",
            fromlist=["BrowserController"],
        ).BrowserController(enumerator=SignInStub()),
    )
    finished = threading.Event()
    logs: list[str] = []
    controller = ClosedLoopController(
        on_log=logs.append,
        on_finished=lambda _r: finished.set(),
        focus_window=lambda _h: True,
    )
    config = ClosedLoopConfig(
        goal="sso test",
        mode=AutomationMode.BROWSER,
        window_handle=9001,
        dry_run=True,
        max_steps=5,
        adapters=stub_adapters(),
    )
    assert controller.start(config)
    time.sleep(0.3)
    assert controller.state == RunnerState.PAUSED
    assert any("Auth pause" in line for line in logs)
    controller.stop()
    controller.join(timeout=3.0)


def test_confirmation_denied_blocks_run():
    ledger = InMemoryLedger()
    finished = threading.Event()
    outcomes: list = []

    def on_finished(result) -> None:
        outcomes.append(result.outcome)
        finished.set()

    deny_adapters = stub_adapters(
        safety_gate=lambda _a, **_k: SafetyDecision(approved=False, reason="denied"),
    )
    controller = ClosedLoopController(
        ledger=ledger,
        on_finished=on_finished,
    )
    controller.start(_stub_config(goal="deny test", max_steps=20, adapters=deny_adapters))
    finished.wait(timeout=5.0)
    assert finished.is_set()
    assert outcomes == [RunOutcome.BLOCKED]
