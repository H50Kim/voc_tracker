"""Persistent ledger: record pending ops before execute and on resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from computer_use.agent.types import (
    Action,
    ActionKind,
    ExecutionOutcome,
    PendingOperation,
)


@dataclass
class LedgerSnapshot:
    pending_operation: PendingOperation | None
    execute_budget_used: int
    result_query_count: int
    semantic_retry_counts: dict[str, int]
    run_outcome: str | None = None


def _action_to_dict(action: Action) -> dict:
    return {
        "kind": action.kind.value,
        "semantic_operation_key": action.semantic_operation_key,
        "description": action.description,
        "target_id": action.target_id,
        "x": action.x,
        "y": action.y,
        "fingerprint": action.fingerprint,
        "operation_id": action.operation_id,
    }


def _action_from_dict(data: dict) -> Action:
    return Action(
        kind=ActionKind(data["kind"]),
        semantic_operation_key=data["semantic_operation_key"],
        description=data["description"],
        target_id=data.get("target_id"),
        x=data.get("x"),
        y=data.get("y"),
        fingerprint=data.get("fingerprint", ""),
        operation_id=data["operation_id"],
    )


def _pending_to_dict(pending: PendingOperation) -> dict:
    return {
        "operation_id": pending.operation_id,
        "semantic_operation_key": pending.semantic_operation_key,
        "action": _action_to_dict(pending.action),
        "execution_outcome": pending.execution_outcome.value,
        "created_at_ms": pending.created_at_ms,
        "ledger_recorded": pending.ledger_recorded,
        "resolved": pending.resolved,
    }


def _pending_from_dict(data: dict) -> PendingOperation:
    return PendingOperation(
        operation_id=data["operation_id"],
        semantic_operation_key=data["semantic_operation_key"],
        action=_action_from_dict(data["action"]),
        execution_outcome=ExecutionOutcome(data["execution_outcome"]),
        created_at_ms=data["created_at_ms"],
        ledger_recorded=data.get("ledger_recorded", True),
        resolved=data.get("resolved", False),
    )


class AgentLedger(Protocol):
    def load(self) -> LedgerSnapshot | None: ...

    def persist_pending_before_execution(self, pending: PendingOperation) -> None: ...

    def persist_resolution(self, operation_id: str, *, resolved: bool) -> None: ...

    def persist_counters(
        self,
        *,
        execute_budget_used: int,
        result_query_count: int,
        semantic_retry_counts: dict[str, int],
    ) -> None: ...

    def mark_run_outcome(self, outcome: str) -> None: ...


class InMemoryLedger:
    """Test-friendly ledger."""

    def __init__(self) -> None:
        self.snapshot: LedgerSnapshot | None = None
        self.pending_writes: list[PendingOperation] = []
        self.resolutions: list[tuple[str, bool]] = []

    def load(self) -> LedgerSnapshot | None:
        return self.snapshot

    def seed(self, snapshot: LedgerSnapshot) -> None:
        self.snapshot = snapshot

    def persist_pending_before_execution(self, pending: PendingOperation) -> None:
        pending.ledger_recorded = True
        self.pending_writes.append(pending)
        if self.snapshot is None:
            self.snapshot = LedgerSnapshot(
                pending_operation=pending,
                execute_budget_used=0,
                result_query_count=0,
                semantic_retry_counts={},
            )
        else:
            self.snapshot.pending_operation = pending

    def persist_resolution(self, operation_id: str, *, resolved: bool) -> None:
        self.resolutions.append((operation_id, resolved))
        if self.snapshot and self.snapshot.pending_operation:
            if self.snapshot.pending_operation.operation_id == operation_id:
                self.snapshot.pending_operation.resolved = resolved

    def persist_counters(
        self,
        *,
        execute_budget_used: int,
        result_query_count: int,
        semantic_retry_counts: dict[str, int],
    ) -> None:
        if self.snapshot is None:
            self.snapshot = LedgerSnapshot(
                pending_operation=None,
                execute_budget_used=execute_budget_used,
                result_query_count=result_query_count,
                semantic_retry_counts=dict(semantic_retry_counts),
            )
        else:
            self.snapshot.execute_budget_used = execute_budget_used
            self.snapshot.result_query_count = result_query_count
            self.snapshot.semantic_retry_counts = dict(semantic_retry_counts)

    def mark_run_outcome(self, outcome: str) -> None:
        if self.snapshot is None:
            self.snapshot = LedgerSnapshot(
                pending_operation=None,
                execute_budget_used=0,
                result_query_count=0,
                semantic_retry_counts={},
                run_outcome=outcome,
            )
        else:
            self.snapshot.run_outcome = outcome


class JsonFileLedger:
    """File-backed ledger for production runs."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> LedgerSnapshot | None:
        if not self._path.exists():
            return None
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        pending = (
            _pending_from_dict(raw["pending_operation"])
            if raw.get("pending_operation")
            else None
        )
        return LedgerSnapshot(
            pending_operation=pending,
            execute_budget_used=int(raw.get("execute_budget_used", 0)),
            result_query_count=int(raw.get("result_query_count", 0)),
            semantic_retry_counts=dict(raw.get("semantic_retry_counts", {})),
            run_outcome=raw.get("run_outcome"),
        )

    def _write(self, snapshot: LedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pending_operation": (
                _pending_to_dict(snapshot.pending_operation)
                if snapshot.pending_operation
                else None
            ),
            "execute_budget_used": snapshot.execute_budget_used,
            "result_query_count": snapshot.result_query_count,
            "semantic_retry_counts": snapshot.semantic_retry_counts,
            "run_outcome": snapshot.run_outcome,
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def persist_pending_before_execution(self, pending: PendingOperation) -> None:
        pending.ledger_recorded = True
        snap = self.load() or LedgerSnapshot(
            pending_operation=None,
            execute_budget_used=0,
            result_query_count=0,
            semantic_retry_counts={},
        )
        snap.pending_operation = pending
        self._write(snap)

    def persist_resolution(self, operation_id: str, *, resolved: bool) -> None:
        snap = self.load()
        if snap is None or snap.pending_operation is None:
            return
        if snap.pending_operation.operation_id != operation_id:
            return
        snap.pending_operation.resolved = resolved
        self._write(snap)

    def persist_counters(
        self,
        *,
        execute_budget_used: int,
        result_query_count: int,
        semantic_retry_counts: dict[str, int],
    ) -> None:
        snap = self.load() or LedgerSnapshot(
            pending_operation=None,
            execute_budget_used=0,
            result_query_count=0,
            semantic_retry_counts={},
        )
        snap.execute_budget_used = execute_budget_used
        snap.result_query_count = result_query_count
        snap.semantic_retry_counts = dict(semantic_retry_counts)
        self._write(snap)

    def mark_run_outcome(self, outcome: str) -> None:
        snap = self.load() or LedgerSnapshot(
            pending_operation=None,
            execute_budget_used=0,
            result_query_count=0,
            semantic_retry_counts={},
        )
        snap.run_outcome = outcome
        self._write(snap)
