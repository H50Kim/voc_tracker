"""Closed-loop agent types (Phase enum, actions, pending ops, policy)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class Phase(str, Enum):
    """External-visible loop phases (§2). WAIT is internal-only."""

    OBSERVE = "observe"
    INTERPRET = "interpret"
    PLAN = "plan"
    SAFETY_GATE = "safety_gate"
    EXECUTE = "execute"
    VERIFY = "verify"
    RESULT_RECHECK = "result_recheck"
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    PAUSED = "paused"  # Auth/MFA or user hold; resume → REOBSERVE (OBSERVE)
    WAIT = "wait"


# Phases allowed after execute budget is exhausted (non-mutating / terminal).
POST_BUDGET_PHASES: frozenset[Phase] = frozenset(
    {Phase.VERIFY, Phase.RESULT_RECHECK, Phase.SUCCESS, Phase.INCOMPLETE}
)


class ExecutionOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class ActionKind(str, Enum):
    """Action kinds; mutating kinds consume EXECUTE budget."""

    OBSERVE = "observe"
    QUERY = "query"
    CLICK = "click"
    TYPE = "type"
    KEY = "key"


MUTATING_KINDS: frozenset[ActionKind] = frozenset(
    {ActionKind.CLICK, ActionKind.TYPE, ActionKind.KEY}
)


def is_mutating_action(action: Action) -> bool:
    return action.kind in MUTATING_KINDS


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    semantic_operation_key: str
    description: str
    target_id: str | None = None
    x: int | None = None
    y: int | None = None
    fingerprint: str = ""
    operation_id: str = field(default_factory=lambda: uuid4().hex)

    def with_coordinates(self, x: int | None, y: int | None, *, target_id: str | None) -> Action:
        return Action(
            kind=self.kind,
            semantic_operation_key=self.semantic_operation_key,
            description=self.description,
            target_id=target_id,
            x=x,
            y=y,
            fingerprint=self.fingerprint,
            operation_id=self.operation_id,
        )


@dataclass
class PendingOperation:
    operation_id: str
    semantic_operation_key: str
    action: Action
    execution_outcome: ExecutionOutcome
    created_at_ms: int
    ledger_recorded: bool = False
    resolved: bool = False


@dataclass(frozen=True)
class AgentPolicy:
    max_execute_budget: int = 3
    max_result_queries: int = 5
    max_retries_per_semantic_key: int = 2


@dataclass
class Observation:
    frame_id: str
    payload: Any = None
    capture_meta: Any = None  # vision.coordinate_engine.CaptureMetadata when set


@dataclass
class Interpretation:
    summary: str
    targets: dict[str, tuple[int, int]]
    confidence: float = 0.0
    fingerprint: str = ""
    uia_labels: dict[str, str] = field(default_factory=dict)
    from_cache: bool = False


@dataclass
class SafetyDecision:
    approved: bool
    requires_reobserve: bool = False
    reason: str = ""


@dataclass
class LoopContext:
    """Mutable runtime state for one run (also partially restored from ledger)."""

    phase: Phase = Phase.OBSERVE
    pending_operation: PendingOperation | None = None
    execute_budget_used: int = 0
    result_query_count: int = 0
    semantic_retry_counts: dict[str, int] = field(default_factory=dict)
    current_action: Action | None = None
    approved_for_execute: Action | None = None
    last_observation: Observation | None = None
    last_interpretation: Interpretation | None = None
    resumed_from_ledger: bool = False
    blocked_mutating: bool = False

    def pending_blocks_mutating(self) -> bool:
        if self.pending_operation is None:
            return False
        return not self.pending_operation.resolved

    def execute_budget_remaining(self, policy: AgentPolicy) -> int:
        return max(0, policy.max_execute_budget - self.execute_budget_used)

    def may_run_mutating_execute(self, policy: AgentPolicy) -> bool:
        if self.pending_blocks_mutating():
            return False
        return self.execute_budget_remaining(policy) > 0
