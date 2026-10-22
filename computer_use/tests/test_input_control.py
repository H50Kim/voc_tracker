import pytest

from computer_use.core.input_control import InputController
from computer_use.policy.policy_guard import PolicyViolation


def test_dry_run_click_no_error():
    ctrl = InputController(dry_run=True)
    ctrl.click(1, 1)


def test_policy_blocks_on_type():
    ctrl = InputController(dry_run=True)
    with pytest.raises(PolicyViolation):
        ctrl.type_text("steal cookie jar")
