"""Auth pause sets Phase.PAUSED without advancing loop."""

from computer_use.agent.adapters import stub_adapters
from computer_use.agent.ledger import InMemoryLedger
from computer_use.agent.loop import step_computer_use
from computer_use.agent.types import AgentPolicy, LoopContext, Phase


def test_paused_phase_is_no_op():
    ctx = LoopContext(phase=Phase.PAUSED)
    result = step_computer_use(
        "goal",
        ctx,
        adapters=stub_adapters(),
        policy=AgentPolicy(),
        ledger=InMemoryLedger(),
    )
    assert result.phase == Phase.PAUSED
    assert result.trace == [Phase.PAUSED]
