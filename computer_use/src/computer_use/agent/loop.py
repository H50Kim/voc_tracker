"""Closed-loop state machine: run_computer_use (§2–§5)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from computer_use.agent.adapters import AdapterBundle
from computer_use.agent.ledger import AgentLedger, LedgerSnapshot
from computer_use.agent.types import (
    Action,
    ActionKind,
    AgentPolicy,
    ExecutionOutcome,
    LoopContext,
    PendingOperation,
    Phase,
    POST_BUDGET_PHASES,
    is_mutating_action,
)


class RunOutcome(str, Enum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"


@dataclass
class RunResult:
    outcome: RunOutcome | None
    phase: Phase
    context: LoopContext
    trace: list[Phase] = field(default_factory=list)


def _now_ms(clock: Callable[[], float]) -> int:
    return int(clock() * 1000)


def _bind_action_coordinates(action: Action, interpretation) -> Action:
    if action.target_id and action.target_id in interpretation.targets:
        x, y = interpretation.targets[action.target_id]
        return action.with_coordinates(x, y, target_id=action.target_id)
    return action


def restore_from_ledger(ctx: LoopContext, snap: LedgerSnapshot) -> None:
    ctx.pending_operation = snap.pending_operation
    ctx.execute_budget_used = snap.execute_budget_used
    ctx.result_query_count = snap.result_query_count
    ctx.semantic_retry_counts = dict(snap.semantic_retry_counts)
    ctx.resumed_from_ledger = True
    if ctx.pending_blocks_mutating():
        ctx.phase = Phase.RESULT_RECHECK
    else:
        ctx.phase = Phase.OBSERVE


def _persist_counters(ctx: LoopContext, ledger: AgentLedger) -> None:
    ledger.persist_counters(
        execute_budget_used=ctx.execute_budget_used,
        result_query_count=ctx.result_query_count,
        semantic_retry_counts=ctx.semantic_retry_counts,
    )


def _semantic_retries_exceeded(ctx: LoopContext, action: Action, policy: AgentPolicy) -> bool:
    count = ctx.semantic_retry_counts.get(action.semantic_operation_key, 0)
    return count >= policy.max_retries_per_semantic_key


def _record_semantic_attempt(ctx: LoopContext, action: Action) -> None:
    key = action.semantic_operation_key
    ctx.semantic_retry_counts[key] = ctx.semantic_retry_counts.get(key, 0) + 1


def _is_rerun_of_pending(ctx: LoopContext, action: Action) -> bool:
    pending = ctx.pending_operation
    if pending is None:
        return False
    return action.operation_id == pending.action.operation_id


def step_computer_use(
    goal: str,
    ctx: LoopContext,
    *,
    adapters: AdapterBundle,
    policy: AgentPolicy,
    ledger: AgentLedger,
    clock: Callable[[], float] | None = None,
    ui_recovery: bool = False,
) -> RunResult:
    """Advance the loop by one phase transition."""
    clock = clock or time.time
    phase = ctx.phase
    ctx.blocked_mutating = False

    if phase == Phase.WAIT:
        ctx.phase = Phase.OBSERVE
        return RunResult(outcome=None, phase=ctx.phase, context=ctx, trace=[Phase.WAIT, Phase.OBSERVE])

    if phase == Phase.OBSERVE:
        ctx.last_observation = adapters.observe()
        ctx.phase = Phase.INTERPRET
        return RunResult(outcome=None, phase=ctx.phase, context=ctx, trace=[Phase.OBSERVE, Phase.INTERPRET])

    if phase == Phase.INTERPRET:
        assert ctx.last_observation is not None
        ctx.last_interpretation = adapters.interpret(ctx.last_observation)
        if ctx.approved_for_execute is not None:
            ctx.approved_for_execute = _bind_action_coordinates(
                ctx.approved_for_execute, ctx.last_interpretation
            )
        ctx.phase = Phase.PLAN
        return RunResult(outcome=None, phase=ctx.phase, context=ctx, trace=[Phase.INTERPRET, Phase.PLAN])

    if phase == Phase.PLAN:
        if ctx.pending_blocks_mutating():
            ctx.phase = Phase.RESULT_RECHECK
            return RunResult(
                outcome=None,
                phase=ctx.phase,
                context=ctx,
                trace=[Phase.PLAN, Phase.RESULT_RECHECK],
            )
        assert ctx.last_interpretation is not None
        candidates = adapters.generate_candidates(ctx.last_interpretation, goal=goal)
        mutating = [c for c in candidates if is_mutating_action(c)]
        if not mutating:
            ctx.phase = Phase.INCOMPLETE
            return RunResult(
                outcome=RunOutcome.INCOMPLETE,
                phase=Phase.INCOMPLETE,
                context=ctx,
                trace=[Phase.PLAN, Phase.INCOMPLETE],
            )
        ctx.current_action = mutating[0]
        ctx.phase = Phase.SAFETY_GATE
        return RunResult(
            outcome=None,
            phase=ctx.phase,
            context=ctx,
            trace=[Phase.PLAN, Phase.SAFETY_GATE],
        )

    if phase == Phase.SAFETY_GATE:
        action = ctx.current_action
        if action is None:
            ctx.phase = Phase.INCOMPLETE
            return RunResult(
                outcome=RunOutcome.INCOMPLETE,
                phase=Phase.INCOMPLETE,
                context=ctx,
                trace=[Phase.SAFETY_GATE, Phase.INCOMPLETE],
            )
        if ctx.pending_blocks_mutating() and is_mutating_action(action):
            ctx.blocked_mutating = True
            ctx.phase = Phase.RESULT_RECHECK
            return RunResult(
                outcome=None,
                phase=ctx.phase,
                context=ctx,
                trace=[Phase.SAFETY_GATE, Phase.RESULT_RECHECK],
            )
        if ui_recovery:
            ctx.approved_for_execute = action
            ctx.phase = Phase.EXECUTE
            return RunResult(
                outcome=None,
                phase=ctx.phase,
                context=ctx,
                trace=[Phase.SAFETY_GATE, Phase.EXECUTE],
            )
        decision = adapters.safety_gate(action, goal=goal)
        if not decision.approved:
            ctx.phase = Phase.INCOMPLETE
            ledger.mark_run_outcome(RunOutcome.BLOCKED.value)
            return RunResult(
                outcome=RunOutcome.BLOCKED,
                phase=Phase.INCOMPLETE,
                context=ctx,
                trace=[Phase.SAFETY_GATE, Phase.INCOMPLETE],
            )
        if decision.requires_reobserve:
            ctx.approved_for_execute = Action(
                kind=action.kind,
                semantic_operation_key=action.semantic_operation_key,
                description=action.description,
                target_id=action.target_id,
                x=None,
                y=None,
                fingerprint=action.fingerprint,
                operation_id=action.operation_id,
            )
            ctx.phase = Phase.OBSERVE
            return RunResult(
                outcome=None,
                phase=ctx.phase,
                context=ctx,
                trace=[Phase.SAFETY_GATE, Phase.OBSERVE],
            )
        ctx.approved_for_execute = action
        ctx.phase = Phase.EXECUTE
        return RunResult(
            outcome=None,
            phase=ctx.phase,
            context=ctx,
            trace=[Phase.SAFETY_GATE, Phase.EXECUTE],
        )

    if phase == Phase.EXECUTE:
        action = ctx.approved_for_execute or ctx.current_action
        if action is None:
            ctx.phase = Phase.INCOMPLETE
            return RunResult(
                outcome=RunOutcome.INCOMPLETE,
                phase=Phase.INCOMPLETE,
                context=ctx,
                trace=[Phase.EXECUTE, Phase.INCOMPLETE],
            )

        if ctx.resumed_from_ledger and ctx.pending_operation is not None:
            if _is_rerun_of_pending(ctx, action):
                ctx.resumed_from_ledger = False
                ctx.phase = Phase.RESULT_RECHECK
                return RunResult(
                    outcome=None,
                    phase=ctx.phase,
                    context=ctx,
                    trace=[Phase.EXECUTE, Phase.RESULT_RECHECK],
                )

        if is_mutating_action(action):
            if ctx.pending_operation and ctx.pending_operation.resolved:
                ctx.pending_operation = None
            if ctx.pending_blocks_mutating():
                ctx.blocked_mutating = True
                ctx.phase = Phase.RESULT_RECHECK
                return RunResult(
                    outcome=None,
                    phase=ctx.phase,
                    context=ctx,
                    trace=[Phase.EXECUTE, Phase.RESULT_RECHECK],
                )
            if _is_rerun_of_pending(ctx, action):
                ctx.phase = Phase.RESULT_RECHECK
                return RunResult(
                    outcome=None,
                    phase=ctx.phase,
                    context=ctx,
                    trace=[Phase.EXECUTE, Phase.RESULT_RECHECK],
                )
            if ctx.execute_budget_remaining(policy) <= 0:
                ctx.phase = Phase.INCOMPLETE
                return RunResult(
                    outcome=RunOutcome.INCOMPLETE,
                    phase=Phase.INCOMPLETE,
                    context=ctx,
                    trace=[Phase.EXECUTE, Phase.INCOMPLETE],
                )
            if _semantic_retries_exceeded(ctx, action, policy):
                ctx.phase = Phase.RESULT_RECHECK
                return RunResult(
                    outcome=None,
                    phase=ctx.phase,
                    context=ctx,
                    trace=[Phase.EXECUTE, Phase.RESULT_RECHECK],
                )

            pending_record = PendingOperation(
                operation_id=action.operation_id,
                semantic_operation_key=action.semantic_operation_key,
                action=action,
                execution_outcome=ExecutionOutcome.UNKNOWN,
                created_at_ms=_now_ms(clock),
            )
            ledger.persist_pending_before_execution(pending_record)
            ctx.pending_operation = pending_record

            _record_semantic_attempt(ctx, action)
            ctx.execute_budget_used += 1
            _persist_counters(ctx, ledger)

            outcome = adapters.execute(action)
            ctx.pending_operation.execution_outcome = outcome

            if outcome == ExecutionOutcome.UNKNOWN:
                ctx.phase = Phase.RESULT_RECHECK
                return RunResult(
                    outcome=None,
                    phase=ctx.phase,
                    context=ctx,
                    trace=[Phase.EXECUTE, Phase.RESULT_RECHECK],
                )

        else:
            adapters.execute(action)

        ctx.phase = Phase.VERIFY
        return RunResult(outcome=None, phase=ctx.phase, context=ctx, trace=[Phase.EXECUTE, Phase.VERIFY])

    if phase == Phase.VERIFY:
        action = ctx.approved_for_execute or ctx.current_action
        after = adapters.observe()
        before = ctx.last_observation
        ctx.last_observation = after
        if action is None:
            ctx.phase = Phase.INCOMPLETE
            return RunResult(
                outcome=RunOutcome.INCOMPLETE,
                phase=Phase.INCOMPLETE,
                context=ctx,
                trace=[Phase.VERIFY, Phase.INCOMPLETE],
            )
        verify_outcome = adapters.verify(action, before=before, after=after)
        if verify_outcome == ExecutionOutcome.SUCCESS:
            if ctx.pending_operation and not ctx.pending_operation.resolved:
                ctx.pending_operation.resolved = True
                ledger.persist_resolution(ctx.pending_operation.operation_id, resolved=True)
            ctx.phase = Phase.SUCCESS
            ledger.mark_run_outcome(RunOutcome.SUCCESS.value)
            return RunResult(
                outcome=RunOutcome.SUCCESS,
                phase=Phase.SUCCESS,
                context=ctx,
                trace=[Phase.VERIFY, Phase.SUCCESS],
            )
        ctx.phase = Phase.RESULT_RECHECK
        return RunResult(
            outcome=None,
            phase=ctx.phase,
            context=ctx,
            trace=[Phase.VERIFY, Phase.RESULT_RECHECK],
        )

    if phase == Phase.RESULT_RECHECK:
        if ctx.result_query_count >= policy.max_result_queries:
            ctx.phase = Phase.INCOMPLETE
            ledger.mark_run_outcome(RunOutcome.INCOMPLETE.value)
            return RunResult(
                outcome=RunOutcome.INCOMPLETE,
                phase=Phase.INCOMPLETE,
                context=ctx,
                trace=[Phase.RESULT_RECHECK, Phase.INCOMPLETE],
            )
        ctx.result_query_count += 1
        _persist_counters(ctx, ledger)
        key = (
            ctx.pending_operation.semantic_operation_key
            if ctx.pending_operation
            else "unknown"
        )
        query_outcome = adapters.result_query(key)
        if query_outcome == ExecutionOutcome.SUCCESS:
            if ctx.pending_operation:
                ctx.pending_operation.resolved = True
                ledger.persist_resolution(ctx.pending_operation.operation_id, resolved=True)
            ctx.phase = Phase.SUCCESS
            ledger.mark_run_outcome(RunOutcome.SUCCESS.value)
            return RunResult(
                outcome=RunOutcome.SUCCESS,
                phase=Phase.SUCCESS,
                context=ctx,
                trace=[Phase.RESULT_RECHECK, Phase.SUCCESS],
            )
        ctx.phase = Phase.RESULT_RECHECK
        return RunResult(
            outcome=None,
            phase=ctx.phase,
            context=ctx,
            trace=[Phase.RESULT_RECHECK, Phase.RESULT_RECHECK],
        )

    if phase in (Phase.SUCCESS, Phase.INCOMPLETE):
        outcome = (
            RunOutcome.SUCCESS if phase == Phase.SUCCESS else RunOutcome.INCOMPLETE
        )
        return RunResult(outcome=outcome, phase=phase, context=ctx, trace=[phase])

    ctx.phase = Phase.INCOMPLETE
    return RunResult(
        outcome=RunOutcome.INCOMPLETE,
        phase=Phase.INCOMPLETE,
        context=ctx,
        trace=[phase, Phase.INCOMPLETE],
    )


def run_computer_use(
    goal: str,
    *,
    adapters: AdapterBundle,
    policy: AgentPolicy | None = None,
    ledger: AgentLedger,
    clock: Callable[[], float] | None = None,
    max_steps: int = 200,
    ui_recovery: bool = False,
    context: LoopContext | None = None,
) -> RunResult:
    """Run until terminal phase or max_steps (§2–§5)."""
    policy = policy or AgentPolicy()
    clock = clock or time.time
    ctx = context or LoopContext()
    trace: list[Phase] = []

    snap = ledger.load()
    if snap is not None and context is None:
        restore_from_ledger(ctx, snap)

    for _ in range(max_steps):
        if ctx.phase in (Phase.SUCCESS, Phase.INCOMPLETE):
            break
        if ctx.execute_budget_remaining(policy) <= 0 and ctx.phase == Phase.EXECUTE:
            action = ctx.approved_for_execute or ctx.current_action
            if action is not None and is_mutating_action(action):
                ctx.phase = Phase.VERIFY
        if ctx.phase not in POST_BUDGET_PHASES and ctx.execute_budget_remaining(policy) <= 0:
            if ctx.phase in (Phase.PLAN, Phase.SAFETY_GATE) and ctx.pending_blocks_mutating():
                ctx.phase = Phase.RESULT_RECHECK
            elif ctx.phase in (Phase.PLAN, Phase.SAFETY_GATE):
                ctx.phase = Phase.INCOMPLETE
                break

        result = step_computer_use(
            goal,
            ctx,
            adapters=adapters,
            policy=policy,
            ledger=ledger,
            clock=clock,
            ui_recovery=ui_recovery,
        )
        trace.extend(result.trace)

    terminal = ctx.phase
    if terminal == Phase.SUCCESS:
        outcome = RunOutcome.SUCCESS
    elif terminal == Phase.INCOMPLETE:
        outcome = RunOutcome.INCOMPLETE
    else:
        outcome = None

    return RunResult(outcome=outcome, phase=terminal, context=ctx, trace=trace)


def internal_wait_then_observe(ctx: LoopContext) -> None:
    """Internal pacing only — not a user-facing recovery path."""
    ctx.phase = Phase.WAIT
