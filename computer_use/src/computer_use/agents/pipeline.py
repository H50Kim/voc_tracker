from dataclasses import dataclass
from enum import Enum


class PauseReason(str, Enum):
    NONE = "none"
    MFA = "mfa"
    USER = "user"


@dataclass
class AgentPipeline:
    """Placeholder for Ollama-backed planner; Phase 1 uses deterministic core only."""

    paused: bool = False
    pause_reason: PauseReason = PauseReason.NONE

    def pause_for_mfa(self) -> None:
        self.paused = True
        self.pause_reason = PauseReason.MFA

    def resume(self) -> None:
        self.paused = False
        self.pause_reason = PauseReason.NONE
