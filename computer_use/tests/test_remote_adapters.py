"""Remote mode adapter wiring (capture clip + coordinate map)."""

from unittest.mock import MagicMock, patch

from PIL import Image

from computer_use.agent.adapters import make_phase1_adapters
from computer_use.agent.types import Action, ActionKind, ExecutionOutcome
from computer_use.controllers.remote_controller import RemoteController, StubRemoteWindowEnumerator
from computer_use.core.region import ScreenRegion
from computer_use.modes.types import AutomationMode


@patch("computer_use.agent.adapters.ScreenCapture")
def test_remote_observe_frame_id_includes_inner(mock_capture_cls):
    mock_capture_cls.return_value.capture_region.return_value = Image.new("RGB", (40, 30))
    remote = RemoteController(enumerator=StubRemoteWindowEnumerator())
    inner = ScreenRegion(10, 10, 400, 300)
    adapters = make_phase1_adapters(
        dry_run=True,
        mode=AutomationMode.REMOTE,
        window_handle=9100,
        remote_controller=remote,
        remote_inner_region=inner,
        region=ScreenRegion(60, 50, 400, 300),
    )
    obs = adapters.observe()
    assert "remote:" in obs.frame_id
    assert "inner:" in obs.frame_id
    assert obs.payload is not None


@patch("computer_use.agent.adapters.ScreenCapture")
def test_remote_execute_maps_capture_relative_coords(mock_capture_cls):
    mock_capture_cls.return_value.capture_region.return_value = Image.new(
        "RGB", (400, 300)
    )
    remote = RemoteController(enumerator=StubRemoteWindowEnumerator())
    inner = ScreenRegion(0, 0, 400, 300)
    adapters = make_phase1_adapters(
        dry_run=True,
        mode=AutomationMode.REMOTE,
        window_handle=9100,
        remote_controller=remote,
        remote_inner_region=inner,
    )
    action = Action(
        kind=ActionKind.CLICK,
        semantic_operation_key="test:click",
        description="click",
        target_id="t",
        x=50,
        y=60,
    )
    outcome = adapters.execute(action)
    assert outcome == ExecutionOutcome.SUCCESS
