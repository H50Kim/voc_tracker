"""§13 closed-loop agent checklist — stubs/fakes only (no Windows)."""

from __future__ import annotations

import pytest

from computer_use.agent.adapters import SafetyDecision, stub_adapters
from computer_use.agent.ledger import InMemoryLedger, LedgerSnapshot
from computer_use.agent.loop import (
    RunOutcome,
    internal_wait_then_observe,
    run_computer_use,
    step_computer_use,
)
from computer_use.agent.types import (
    Action,
    ActionKind,
    AgentPolicy,
    ExecutionOutcome,
    Interpretation,
    LoopContext,
    Observation,
    PendingOperation,
    Phase,
)
# §13 checklist ids (design spec 2026-10-26)
CHECKLIST = {
    "13.1": "pending blocks new mutating actions",
    "13.2": "pending blocks re-execution of original operation",
    "13.3": "EXECUTE budget enforced only before mutating EXECUTE",
    "13.4": "VERIFY allowed after execute budget exhausted",
    "13.5": "RESULT_RECHECK allowed after execute budget exhausted",
    "13.6": "SUCCESS via verification after budget exhausted",
    "13.7": "UNKNOWN execution does not retry same mutating operation",
    "13.8": "max_result_queries yields INCOMPLETE with unresolved pending",
    "13.9": "REOBSERVE after approval reidentifies target (no stale coordinates)",
    "13.10": "retry limits use semantic_operation_key not fingerprint alone",
    "13.11": "ledger persists pending before mutating execution",
    "13.12": "ledger persists resolution on success",
    "13.13": "restart does not auto re-run pending mutating operation",
    "13.14": "WAIT/OBSERVE pacing is internal-only (not user recovery)",
    "13.15": "UI recovery transitions SAFETY_GATE → EXECUTE",
}


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float = 1.0) -> None:
        self.t += seconds


def _click_action(
    *,
    sem_key: str = "op:submit",
    op_id: str = "op-1",
    fingerprint: str = "fp-a",
    x: int | None = 10,
    y: int | None = 20,
) -> Action:
    return Action(
        kind=ActionKind.CLICK,
        semantic_operation_key=sem_key,
        description="click submit",
        target_id="submit",
        x=x,
        y=y,
        fingerprint=fingerprint,
        operation_id=op_id,
    )


def test_13_1_pending_blocks_new_mutating():
    pending = PendingOperation(
        operation_id="op-pending",
        semantic_operation_key="op:save",
        action=_click_action(op_id="op-pending"),
        execution_outcome=ExecutionOutcome.UNKNOWN,
        created_at_ms=1,
    )
    ctx = LoopContext(phase=Phase.PLAN, pending_operation=pending)
    ledger = InMemoryLedger()
    adapters = stub_adapters()
    result = step_computer_use(
        "save",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    assert result.phase == Phase.RESULT_RECHECK
    assert CHECKLIST["13.1"]


def test_13_2_pending_blocks_rerun_original_operation():
    action = _click_action(op_id="same-op")
    pending = PendingOperation(
        operation_id="same-op",
        semantic_operation_key=action.semantic_operation_key,
        action=action,
        execution_outcome=ExecutionOutcome.UNKNOWN,
        created_at_ms=1,
    )
    ctx = LoopContext(
        phase=Phase.EXECUTE,
        pending_operation=pending,
        approved_for_execute=action,
    )
    ledger = InMemoryLedger()
    execute_calls: list[str] = []

    def execute(a: Action) -> ExecutionOutcome:
        execute_calls.append(a.operation_id)
        return ExecutionOutcome.SUCCESS

    adapters = stub_adapters(execute=execute)
    step_computer_use(
        "goal",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    assert execute_calls == []
    assert ctx.phase == Phase.RESULT_RECHECK
    assert CHECKLIST["13.2"]


def test_13_3_execute_budget_only_before_mutating_execute():
    policy = AgentPolicy(max_execute_budget=1)
    ctx = LoopContext(phase=Phase.EXECUTE, approved_for_execute=_click_action())
    ledger = InMemoryLedger()
    ctx.execute_budget_used = 1
    adapters = stub_adapters()
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=policy,
        ledger=ledger,
        clock=FakeClock(),
    )
    assert ctx.phase == Phase.INCOMPLETE
    assert CHECKLIST["13.3"]


def test_13_4_verify_allowed_after_budget_exhausted():
    policy = AgentPolicy(max_execute_budget=0)
    ctx = LoopContext(
        phase=Phase.VERIFY,
        approved_for_execute=_click_action(),
        execute_budget_used=5,
    )
    ledger = InMemoryLedger()
    adapters = stub_adapters()
    result = step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=policy,
        ledger=ledger,
        clock=FakeClock(),
    )
    assert result.phase == Phase.SUCCESS
    assert CHECKLIST["13.4"]


def test_13_5_result_recheck_allowed_after_budget_exhausted():
    policy = AgentPolicy(max_execute_budget=0, max_result_queries=3)
    pending = PendingOperation(
        operation_id="p1",
        semantic_operation_key="op:x",
        action=_click_action(op_id="p1"),
        execution_outcome=ExecutionOutcome.UNKNOWN,
        created_at_ms=1,
    )
    ctx = LoopContext(
        phase=Phase.RESULT_RECHECK,
        pending_operation=pending,
        execute_budget_used=99,
        result_query_count=0,
    )
    ledger = InMemoryLedger()

    def query(_key: str) -> ExecutionOutcome:
        return ExecutionOutcome.UNKNOWN

    adapters = stub_adapters(result_query=query)
    result = step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=policy,
        ledger=ledger,
        clock=FakeClock(),
    )
    assert result.phase == Phase.RESULT_RECHECK
    assert ctx.result_query_count == 1
    assert CHECKLIST["13.5"]


def test_13_6_success_after_budget_exhausted_via_recheck():
    policy = AgentPolicy(max_execute_budget=0, max_result_queries=2)
    pending = PendingOperation(
        operation_id="p1",
        semantic_operation_key="op:x",
        action=_click_action(op_id="p1"),
        execution_outcome=ExecutionOutcome.UNKNOWN,
        created_at_ms=1,
    )
    ctx = LoopContext(
        phase=Phase.RESULT_RECHECK,
        pending_operation=pending,
        execute_budget_used=10,
    )
    ledger = InMemoryLedger()

    def query(_key: str) -> ExecutionOutcome:
        return ExecutionOutcome.SUCCESS

    adapters = stub_adapters(result_query=query)
    result = step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=policy,
        ledger=ledger,
        clock=FakeClock(),
    )
    assert result.outcome == RunOutcome.SUCCESS
    assert pending.resolved is True
    assert CHECKLIST["13.6"]


def test_13_7_unknown_execution_no_retry_same_mutating_op():
    action = _click_action(op_id="once")
    ctx = LoopContext(phase=Phase.EXECUTE, approved_for_execute=action)
    ledger = InMemoryLedger()
    attempts: list[str] = []

    def execute(a: Action) -> ExecutionOutcome:
        attempts.append(a.operation_id)
        return ExecutionOutcome.UNKNOWN

    adapters = stub_adapters(execute=execute)
    policy = AgentPolicy(max_retries_per_semantic_key=5)
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=policy,
        ledger=ledger,
        clock=FakeClock(),
    )
    assert attempts == ["once"]
    ctx.approved_for_execute = action
    ctx.phase = Phase.EXECUTE
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=policy,
        ledger=ledger,
        clock=FakeClock(),
    )
    assert attempts == ["once"]
    assert CHECKLIST["13.7"]


def test_13_8_max_result_queries_incomplete_unresolved_pending():
    policy = AgentPolicy(max_result_queries=2)
    pending = PendingOperation(
        operation_id="p1",
        semantic_operation_key="op:x",
        action=_click_action(op_id="p1"),
        execution_outcome=ExecutionOutcome.UNKNOWN,
        created_at_ms=1,
    )
    ctx = LoopContext(
        phase=Phase.RESULT_RECHECK,
        pending_operation=pending,
        result_query_count=2,
    )
    ledger = InMemoryLedger()
    adapters = stub_adapters()
    result = step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=policy,
        ledger=ledger,
        clock=FakeClock(),
    )
    assert result.outcome == RunOutcome.INCOMPLETE
    assert pending.resolved is False
    assert CHECKLIST["13.8"]


def test_13_9_reobserve_after_approval_reidentifies_target():
    action = _click_action(x=None, y=None)
    ctx = LoopContext(phase=Phase.SAFETY_GATE, current_action=action)
    ledger = InMemoryLedger()
    coords_seen: list[tuple[int | None, int | None]] = []

    def safety(a: Action, *, goal: str) -> SafetyDecision:
        _ = goal
        coords_seen.append((a.x, a.y))
        return SafetyDecision(approved=True, requires_reobserve=True)

    def interpret(obs: Observation) -> Interpretation:
        return Interpretation(summary=obs.frame_id, targets={"submit": (99, 88)})

    adapters = stub_adapters(safety_gate=safety, interpret=interpret)
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    assert ctx.phase == Phase.OBSERVE
    assert ctx.approved_for_execute is not None
    assert ctx.approved_for_execute.x is None

    ctx.phase = Phase.OBSERVE
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    ctx.phase = Phase.INTERPRET
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    assert ctx.approved_for_execute is not None
    assert ctx.approved_for_execute.x == 99
    assert ctx.approved_for_execute.y == 88
    assert CHECKLIST["13.9"]


def test_13_10_semantic_key_retry_limit_not_fingerprint():
    policy = AgentPolicy(max_retries_per_semantic_key=1)
    ledger = InMemoryLedger()
    exec_count = 0

    def execute(a: Action) -> ExecutionOutcome:
        nonlocal exec_count
        exec_count += 1
        _ = a
        return ExecutionOutcome.SUCCESS

    adapters = stub_adapters(execute=execute)
    first = _click_action(fingerprint="fp-1", op_id="id-1")
    ctx = LoopContext(phase=Phase.EXECUTE, approved_for_execute=first)
    step_computer_use("g", ctx, adapters=adapters, policy=policy, ledger=ledger, clock=FakeClock())
    assert exec_count == 1

    ctx.pending_operation = None
    ctx.pending_operation = PendingOperation(
        operation_id="id-1",
        semantic_operation_key=first.semantic_operation_key,
        action=first,
        execution_outcome=ExecutionOutcome.SUCCESS,
        created_at_ms=1,
        resolved=True,
    )
    second = _click_action(fingerprint="fp-2", op_id="id-2")
    ctx.phase = Phase.EXECUTE
    ctx.approved_for_execute = second
    step_computer_use("g", ctx, adapters=adapters, policy=policy, ledger=ledger, clock=FakeClock())
    assert exec_count == 1
    assert ctx.phase == Phase.RESULT_RECHECK
    assert CHECKLIST["13.10"]


def test_13_11_ledger_persists_before_execution():
    ledger = InMemoryLedger()
    ctx = LoopContext(phase=Phase.EXECUTE, approved_for_execute=_click_action(op_id="pre"))
    adapters = stub_adapters()
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    assert len(ledger.pending_writes) == 1
    assert ledger.pending_writes[0].ledger_recorded is True
    assert CHECKLIST["13.11"]


def test_13_12_ledger_persists_resolution_on_success():
    ledger = InMemoryLedger()
    ctx = LoopContext(phase=Phase.VERIFY, approved_for_execute=_click_action(op_id="r1"))
    ctx.pending_operation = PendingOperation(
        operation_id="r1",
        semantic_operation_key="op:submit",
        action=_click_action(op_id="r1"),
        execution_outcome=ExecutionOutcome.UNKNOWN,
        created_at_ms=1,
    )
    adapters = stub_adapters()
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    assert ("r1", True) in ledger.resolutions
    assert CHECKLIST["13.12"]


def test_13_13_restart_does_not_auto_rerun_pending():
    action = _click_action(op_id="resume-op")
    pending = PendingOperation(
        operation_id="resume-op",
        semantic_operation_key=action.semantic_operation_key,
        action=action,
        execution_outcome=ExecutionOutcome.UNKNOWN,
        created_at_ms=1,
        ledger_recorded=True,
    )
    ledger = InMemoryLedger()
    ledger.seed(
        LedgerSnapshot(
            pending_operation=pending,
            execute_budget_used=1,
            result_query_count=0,
            semantic_retry_counts={},
        )
    )
    exec_calls: list[str] = []

    def execute(a: Action) -> ExecutionOutcome:
        exec_calls.append(a.operation_id)
        return ExecutionOutcome.SUCCESS

    adapters = stub_adapters(execute=execute)
    result = run_computer_use(
        "g",
        adapters=adapters,
        policy=AgentPolicy(max_result_queries=1),
        ledger=ledger,
        clock=FakeClock(),
        max_steps=5,
    )
    assert exec_calls == []
    assert result.context.resumed_from_ledger is True
    assert result.context.pending_operation is not None
    assert result.context.pending_operation.resolved is False
    assert CHECKLIST["13.13"]


def test_13_14_wait_observe_internal_not_user_recovery():
    ctx = LoopContext(phase=Phase.SAFETY_GATE, current_action=_click_action())
    internal_wait_then_observe(ctx)
    assert ctx.phase == Phase.WAIT
    ledger = InMemoryLedger()
    adapters = stub_adapters()
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    assert ctx.phase == Phase.OBSERVE
    step_computer_use(
        "g",
        ctx,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
    )
    assert ctx.phase == Phase.INTERPRET
    recovery = LoopContext(phase=Phase.SAFETY_GATE, current_action=_click_action())
    adapters = stub_adapters()
    result = step_computer_use(
        "g",
        recovery,
        adapters=adapters,
        policy=AgentPolicy(),
        ledger=ledger,
        clock=FakeClock(),
        ui_recovery=True,
    )
    assert result.trace == [Phase.SAFETY_GATE, Phase.EXECUTE]
    assert CHECKLIST["13.14"] and CHECKLIST["13.15"]


def test_checklist_covers_all_13_items():
    assert len(CHECKLIST) == 15
    for key in [f"13.{i}" for i in range(1, 16)]:
        assert key in CHECKLIST
