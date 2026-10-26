from dataclasses import dataclass, field
from enum import Enum

from computer_use.ai.model_manager import ModelManager


class PauseReason(str, Enum):
    NONE = "none"
    MFA = "mfa"
    USER = "user"


@dataclass
class AgentPipeline:
    """Ollama-backed planner/perception facade; executor stays deterministic."""

    paused: bool = False
    pause_reason: PauseReason = PauseReason.NONE
    model_manager: ModelManager = field(default_factory=ModelManager)

    def startup(self) -> None:
        self.model_manager.startup()

    def pause_for_mfa(self) -> None:
        self.paused = True
        self.pause_reason = PauseReason.MFA

    def resume(self) -> None:
        self.paused = False
        self.pause_reason = PauseReason.NONE

    @property
    def model_status(self) -> str:
        return self.model_manager.status_summary()
